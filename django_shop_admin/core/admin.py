from django.contrib import admin
from django.contrib.admin.widgets import AdminFileWidget
from django.utils.safestring import mark_safe
from .models import Shop, Category, Product
from django.db.models import ImageField, Q
from django import forms
from admin_numeric_filter.admin import RangeNumericFilter, NumericFilterModelAdmin
from django.utils.html import format_html
from django.urls import path, reverse
from django.template.response import TemplateResponse

# Register your models here.
class AdminImageWidget(AdminFileWidget):
	def render(self, name, value, attrs=None, renderer=None):
		output = []
		if value and getattr(value, "url", None):
			image_url = value.url
			file_name = str(value)
			output.append(u' <a href="%s" target="_blank"><img src="%s" alt="%s" width="200" height="200"  style="object-fit: cover;"/></a><br>%s ' % \
				(image_url, image_url, file_name, 'Изменить:'))
		output.append(super(AdminFileWidget, self).render(name, value, attrs))
		return mark_safe(u''.join(output))


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
	list_display = ('title',)
	search_fields = ('title',)
	ordering = ('title',)
	readonly_fields = ('id',)
	formfield_overrides = {ImageField: {'widget': AdminImageWidget}}


class ParentCategoryFilter(admin.SimpleListFilter):
	title = 'Род. категория'
	parameter_name = 'parents__id'

	def lookups(self, request, model_admin):
		objs = Category.objects.all().only('title').order_by('title')
		return [(o.pk, o.title) for o in objs]

	def queryset(self, request, queryset):
		value = self.value()
		if value is not None:
			return queryset.filter(parents__id=self.value())
		return queryset


class CategoryAdminForm(forms.ModelForm):
	class Meta:
		model = Category
		fields = ('id', 'title', 'description', 'parents')

	def __init__(self, *args, **kwargs):
		super(CategoryAdminForm, self).__init__(*args, **kwargs)
		instance = kwargs.get("instance")
		if instance:
			self.fields['parents'].queryset = Category.objects.filter(~(Q(pk=instance.pk)|Q(pk__in=instance.children.values('id'))))


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ('title','category_actions')
	search_fields = ('products__id', 'title')
	list_filter = (ParentCategoryFilter,)
	ordering = ('title',)
	readonly_fields = ('id',)
	form = CategoryAdminForm
	filter_horizontal = ('parents',)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<int:category_id>/paths/',
				self.admin_site.admin_view(self.process_paths),
				name='category-paths',
			),
		]
		return custom_urls + urls    

	def category_actions(self, obj):
		return format_html(
			'<a class="button" href="{}">Показать пути</a>',
			reverse('admin:category-paths', args=[obj.pk])
		)

	category_actions.short_description = 'Действия'
	category_actions.allow_tags = True

	def process_paths(self, request, category_id, *args, **kwargs):
		obj = self.get_object(request, category_id)
		context = self.admin_site.each_context(request)
		context['opts'] = self.model._meta
		paths = list(obj.get_all_paths())
		context['paths'] = paths
		context['title'] = f'Пути к категории {obj.title} ({len(paths)})'        
		return TemplateResponse(
			request,
			'admin/category_paths.html',
			context,
		)


class ShopFilter(admin.SimpleListFilter):
	title = 'Магазин'
	parameter_name = 'shop__id'

	def lookups(self, request, model_admin):
		objs = Shop.objects.all().only('title').order_by('title')
		return [(o.pk, o.title) for o in objs]

	def queryset(self, request, queryset):
		value = self.value()
		if value is not None:
			return queryset.filter(shop__id=self.value())
		return queryset


class CategoryFilter(admin.SimpleListFilter):
	title = 'Категория'
	parameter_name = 'categories__id'

	def lookups(self, request, model_admin):
		objs = Category.objects.all().only('title').order_by('title')
		return [(o.pk, o.title) for o in objs]

	def queryset(self, request, queryset):
		value = self.value()
		if value is not None:
			return queryset.filter(categories__id=self.value())
		return queryset


class MyNumericRangeFilter(RangeNumericFilter):
	template = 'admin/filter_numeric_range.html'


@admin.register(Product)
class ProductAdmin(NumericFilterModelAdmin):
	list_display = ('title', 'id', 'amount', 'price', 'active', 'shop')
	search_fields = ('id', 'title')
	list_filter = ('active',('price',MyNumericRangeFilter), 
		ShopFilter, CategoryFilter)
	readonly_fields = ('id',)
	filter_horizontal = ('categories',)

