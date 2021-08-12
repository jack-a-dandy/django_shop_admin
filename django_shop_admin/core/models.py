from django.db.models import (Model, CharField, TextField, ImageField, 
	BooleanField, PositiveIntegerField, FloatField, ForeignKey, ManyToManyField,
	CASCADE, CheckConstraint, Q)
from django.conf import settings

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
	parents = ManyToManyField('self', symmetrical=False, related_name='children')

	def __str__(self):
		return self.title

	class Meta:
		db_table = 'categories'
		verbose_name = "Категория"
		verbose_name_plural = "Категории"
		constraints = (
				CheckConstraint(check=Q(title__iregex=r'^\S.*\S$'), name='category_title_check'),
		)


class Product(Model):
	title = CharField(verbose_name='Название', max_length=200, db_index=True)
	description = TextField(verbose_name='Описание')
	amount = PositiveIntegerField(verbose_name='Кол-во')
	price = FloatField(verbose_name='Цена')
	active = BooleanField(default=True, blank=True)
	shop = ForeignKey(Shop, on_delete=CASCADE, related_name='products')
	categories = ManyToManyField(Category, related_name='products')

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
