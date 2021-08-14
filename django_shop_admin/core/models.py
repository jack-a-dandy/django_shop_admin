from django.db.models import (Model, CharField, TextField, ImageField, 
	BooleanField, PositiveIntegerField, DecimalField, ForeignKey, ManyToManyField,
	CASCADE, CheckConstraint, UniqueConstraint, Q, F)
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed

# Create your models here.

class Shop(Model):
	title = CharField(verbose_name='Название', max_length=200, unique=True)
	description = TextField(verbose_name='Описание', null=True, blank=True)
	imageUrl = ImageField(verbose_name="Фото", null=True, blank=True, 
		upload_to=f'{settings.IMAGES_DIR}/shops/')

	def __str__(self):
		return self.title

	class Meta:
		db_table = 'shops'
		verbose_name = "Магазин"
		verbose_name_plural = "Магазины"
		constraints = (
				CheckConstraint(check=Q(title__iregex=r'^\S.*\S$'), name='shop_title_check'),
		)


class Category(Model):
	title = CharField(verbose_name='Название', max_length=200, unique=True)
	description = TextField(verbose_name='Описание', null=True, blank=True)
	parents = ManyToManyField('self', symmetrical=False, through='CategoryParent', 
		blank=True, verbose_name='Родительские категории')

	def __str__(self):
		return self.title

	def get_all_paths(self):
		if self.parents:
			for paths, title in ((list(x.get_all_paths()), x.title) for x in self.parents.only('title').order_by('title').iterator()):
				if not paths:
					yield title+' / '
				else:
					for p in paths:
						yield p+title+' / '
		else:
			yield []

	class Meta:
		db_table = 'categories'
		verbose_name = "Категория"
		verbose_name_plural = "Категории"
		constraints = (
				CheckConstraint(check=Q(title__iregex=r'^\S.*\S$'), name='category_title_check'),
		)


class CategoryParent(Model):
	from_category = ForeignKey(Category, on_delete=CASCADE, 
		verbose_name='Дочерняя категория')
	to_category = ForeignKey(Category, on_delete=CASCADE, 
		related_name='from_category', verbose_name='Родительская категория')

	class Meta:
		constraints = (
				UniqueConstraint(fields=('from_category', 'to_category'), name='unique_category_parent'),
				CheckConstraint(check=~Q(from_category=F('to_category')), name='self_parent_category_check')
			)
		verbose_name = "Отношение категорий"
		verbose_name_plural = "Отношения категорий"

	@transaction.atomic
	def save(self, *args, **kwargs):
		check_child_in_parents(self.from_category_id, self.to_category_id, self.to_category_id)
		super(CategoryParent, self).save(*args, **kwargs)


def check_child_in_parents(from_id, to_id, start_to, checked=set()):
	if CategoryParent.objects.filter(from_category_id=to_id, to_category_id=from_id).exists():
			raise ValidationError(f'Доч. категория {Category.objects.get(id=from_id).title} не может быть родительской '\
				f"для {Category.objects.filter(pk=start_to).values_list('title', flat=True)[0]} "\
				f"({Category.objects.filter(pk=to_id).values_list('title', flat=True)[0]}).")
	else:
		for i in CategoryParent.objects.filter(from_category_id=to_id).values_list('to_category_id', flat=True):
			if i not in checked:
				checked.add(i)
				check_child_in_parents(from_id, i, start_to, checked)


def process_m2m_category_update(sender, instance, action, reverse, pk_set, **kwargs):
	if action == 'pre_add':
		if reverse:
			for k in pk_set:
				check_child_in_parents(k, instance.pk, instance.pk)
		else:
			for k in pk_set:
				check_child_in_parents(instance.pk, k, k)
	

m2m_changed.connect(process_m2m_category_update, sender=CategoryParent)


class Product(Model):
	title = CharField(verbose_name='Название', max_length=200, db_index=True)
	description = TextField(verbose_name='Описание', null=True, blank=True)
	amount = PositiveIntegerField(verbose_name='Кол-во')
	price = DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена')
	active = BooleanField(default=True, blank=True, verbose_name='Активен')
	shop = ForeignKey(Shop, on_delete=CASCADE, related_name='products', verbose_name='Магазин')
	categories = ManyToManyField(Category, related_name='products', verbose_name='Категории')

	def __str__(self):
		return self.title

	class Meta:
		db_table = 'products'
		verbose_name = "Продукт"
		verbose_name_plural = "Продукты"
		constraints = (
				CheckConstraint(check=Q(title__iregex=r'^\S.*\S$'), name='product_title_check'),
				CheckConstraint(check=Q(price__gte=0), name='price_gte_0'),
			)
