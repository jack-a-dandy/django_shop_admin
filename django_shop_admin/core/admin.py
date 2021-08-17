from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from .models import Shop, Category, Product, ProductImage
from django.db.models import ImageField, Q
from django import forms
from admin_numeric_filter.admin import RangeNumericFilter, NumericFilterModelAdmin
from .widgets import ImageWidget, FilteredSelectMultipleWithReadonlyMode
from django.utils.html import format_html
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.db import transaction
from django.contrib.admin.options import (
	PermissionDenied, unquote, DisallowedModelAdminToField,
	flatten_fieldsets, all_valid, IS_POPUP_VAR, TO_FIELD_VAR, 
	helpers, _
)
from django.conf import settings
from django.forms.models import BaseInlineFormSet
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.template.defaultfilters import truncatechars

# Register your models here.
admin.site.site_header = 'Администрация'
admin.site.site_title = 'Администрация'


class ManagedShopsInlineAdmin(admin.TabularInline):
	model = Shop.product_managers.through
	extra = 0
	verbose_name_plural = 'Связанные магазины'
	verbose_name = 'Магазин'


class CustomUserAdmin(UserAdmin):
	def get_inlines(self, request, obj):
		if obj.managed_shops or obj.groups.filter(name='product managers').exists():
			return (ManagedShopsInlineAdmin,)
		else:
			return ()

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


class ShortDescriptionListFieldMixin:
	short_description_length = 160

	def short_description(self, instance):
		return truncatechars(instance.description, self.short_description_length)

	short_description.short_description = 'Описание'


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin, ShortDescriptionListFieldMixin):
	list_display = ('title','image','id', 'short_description')
	search_fields = ('title',)
	ordering = ('title',)
	readonly_fields = ('id',)
	formfield_overrides = {ImageField: {'widget': ImageWidget}}
	filter_horizontal = ('product_managers',)

	def image(self, instance):
		url = instance.imageUrl
		if url:
			return format_html("<img src='{}/{}' width=100 height=100 style='object-fit:contain' />",
				settings.MEDIA_URL, url)
		else:
			return format_html("<img alt='—' />")

	image.short_description = 'Фото'

	def get_fields(self, request, obj=None):
		if request.user.is_superuser:
			return ('id', 'title', 'description', 'imageUrl', 'product_managers')
		else:
			return ('id', 'title', 'description', 'imageUrl')

	def get_queryset(self, request):
		if request.user.is_superuser:
			return super().get_queryset(request)
		else:
			return request.user.managed_shops.order_by(*self.ordering)

	def can_access_object(self, request, obj):
		if obj is None:
			return True
		return request.user.managed_shops.filter(id=obj.id).exists()

	def has_view_permission(self, request, obj=None):
		if request.user.is_superuser:
			return True
		else:
			if super().has_view_permission(request, obj):
				return self.can_access_object(request, obj)
			else:
				return False


class ParentCategoryFilter(admin.SimpleListFilter):
	title = 'Род. категория'
	parameter_name = 'parents__id'

	def lookups(self, request, model_admin):
		objs = Category.objects.filter(from_category__isnull=False).only('title').distinct().order_by('title')
		return [(o.pk, o.title) for o in objs]

	def queryset(self, request, queryset):
		value = self.value()
		if value is not None:
			return queryset.filter(parents__id=self.value())
		return queryset


class CategoryAdminForm(forms.ModelForm):
	parents = forms.ModelMultipleChoiceField(label='Родительские категории',
				queryset = Category.objects.only('title').order_by('title'),
				required=False,
				widget=FilteredSelectMultiple(
						verbose_name='Родительские категории',
						is_stacked=False
					))

	children = forms.ModelMultipleChoiceField(label='Дочерние категории',
				queryset=Category.objects.only('title').order_by('title'),
				required=False,
				widget=FilteredSelectMultipleWithReadonlyMode(
						verbose_name='Дочерние категории',
						is_stacked=False
					)
				)

	class Meta:
		model = Category
		fields = '__all__'

	def __init__(self, *args, **kwargs):
		super(CategoryAdminForm, self).__init__(*args, **kwargs)
		instance = kwargs.get("instance")
		if instance and instance.pk:
			self.fields['parents'].queryset=Category.objects.filter(
						~(Q(pk=instance.pk)|Q(pk__in=instance.category_set.values('id')))
						).only('title').order_by('title')
			self.fields['parents'].initial=instance.parents.all()
			self.fields['children'].queryset=Category.objects.filter(
							~(Q(pk=instance.pk)|Q(pk__in=instance.parents.values('id')))
					).only('title').order_by('title')
			self.fields['children'].initial=instance.category_set.all()
			self.fields['children'].widget.attrs['readonly']=True

	def save(self, commit=True):
		category = super(CategoryAdminForm, self).save(commit=False)
		if commit:
			error=1
			try:
				with transaction.atomic():
					category.save()
					data = self.cleaned_data['parents']
					if self.fields['parents'].has_changed(self.fields['parents'].initial, data):
						category.parents.set(data)
					error=2
					data = self.cleaned_data['children']
					if self.fields['children'].has_changed(self.fields['children'].initial, data):
						category.category_set.set(data)
			except forms.ValidationError as e:
				self.add_error('parents' if error==1 else 'children', e)
			except Exception as e:
				self.add_error(None, e)
		return category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin, ShortDescriptionListFieldMixin):
	list_display = ('title','id', 'short_description', 'category_actions')
	search_fields = ('products__id', 'title')
	list_filter = (ParentCategoryFilter,)
	ordering = ('title',)
	readonly_fields = ('id',)
	form = CategoryAdminForm

	change_form_template = 'admin/category_change_form.html'

	def get_fields(self, request, obj=None):
		return ('id', 'title', 'description', 'parents', 'children')

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

	def save_form(self, request, form, change):
		return form.save()

	#Немного отредактированный метод класса ModelAdmin 
	#для отображения ошибок при сохранении родительских/дочерних категорий
	def _changeform_view(self, request, object_id, form_url, extra_context):
		to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
		if to_field and not self.to_field_allowed(request, to_field):
			raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

		model = self.model
		opts = model._meta

		if request.method == 'POST' and '_saveasnew' in request.POST:
			object_id = None

		add = object_id is None

		if add:
			if not self.has_add_permission(request):
				raise PermissionDenied
			obj = None

		else:
			obj = self.get_object(request, unquote(object_id), to_field)

			if request.method == 'POST':
				if not self.has_change_permission(request, obj):
					raise PermissionDenied
			else:
				if not self.has_view_or_change_permission(request, obj):
					raise PermissionDenied

			if obj is None:
				return self._get_obj_does_not_exist_redirect(request, opts, object_id)

		fieldsets = self.get_fieldsets(request, obj)
		ModelForm = self.get_form(
			request, obj, change=not add, fields=flatten_fieldsets(fieldsets)
		)
		if request.method == 'POST':
			form = ModelForm(request.POST, request.FILES, instance=obj)
			form_validated = form.is_valid()
			if form_validated:
				new_object = self.save_form(request, form, change=not add)
				form_validated = form.is_valid()
			else:
				new_object = form.instance
			formsets, inline_instances = self._create_formsets(request, new_object, change=not add)
			if all_valid(formsets) and form_validated:
				change_message = self.construct_change_message(request, form, formsets, add)
				if add:
					self.log_addition(request, new_object, change_message)
					return self.response_add(request, new_object)
				else:
					self.log_change(request, new_object, change_message)
					return self.response_change(request, new_object)
			else:
				form_validated = False
		else:
			if add:
				initial = self.get_changeform_initial_data(request)
				form = ModelForm(initial=initial)
				formsets, inline_instances = self._create_formsets(request, form.instance, change=False)
			else:
				form = ModelForm(instance=obj)
				formsets, inline_instances = self._create_formsets(request, obj, change=True)

		if not add and not self.has_change_permission(request, obj):
			#readonly_fields = flatten_fieldsets(fieldsets)
			readonly_fields = ['id','title','description', 'parents']
			form.fields['children'].to_field_name='title'
			form.fields['children'].widget.attrs['readonly']=True
		else:
			readonly_fields = self.get_readonly_fields(request, obj)
		adminForm = helpers.AdminForm(
			form,
			list(fieldsets),
			# Clear prepopulated fields on a view-only form to avoid a crash.
			self.get_prepopulated_fields(request, obj) if add or self.has_change_permission(request, obj) else {},
			readonly_fields,
			model_admin=self)
		media = self.media + adminForm.media

		inline_formsets = self.get_inline_formsets(request, formsets, inline_instances, obj)
		for inline_formset in inline_formsets:
			media = media + inline_formset.media

		if add:
			title = _('Add %s')
		elif self.has_change_permission(request, obj):
			title = _('Change %s')
		else:
			title = _('View %s')
		context = {
			**self.admin_site.each_context(request),
			'title': title % opts.verbose_name,
			'subtitle': str(obj) if obj else None,
			'adminform': adminForm,
			'object_id': object_id,
			'original': obj,
			'is_popup': IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
			'to_field': to_field,
			'media': media,
			'inline_admin_formsets': inline_formsets,
			'errors': helpers.AdminErrorList(form, formsets),
			'preserved_filters': self.get_preserved_filters(request),
		}

		# Hide the "Save" and "Save and continue" buttons if "Save as New" was
		# previously chosen to prevent the interface from getting confusing.
		if request.method == 'POST' and not form_validated and "_saveasnew" in request.POST:
			context['show_save'] = False
			context['show_save_and_continue'] = False
			# Use the change template instead of the add template.
			add = False

		context.update(extra_context or {})

		return self.render_change_form(request, context, add=add, change=not add, obj=obj, form_url=form_url)


class ShopFilter(admin.SimpleListFilter):
	title = 'Магазин'
	parameter_name = 'shop__id'

	def lookups(self, request, model_admin):
		objs = Shop.objects if request.user.is_superuser else request.user.managed_shops
		objs = objs.filter(products__isnull=False).only('title').distinct().order_by('title')
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
		filters = {'products__isnull': False}
		if not request.user.is_superuser:
			filters['products__shop__id__in']=request.user.managed_shops.values_list('id', flat=True)
		objs = Category.objects.filter(**filters).only('title').distinct().order_by('title')
		return [(o.pk, o.title) for o in objs]

	def queryset(self, request, queryset):
		value = self.value()
		if value is not None:
			return queryset.filter(categories__id=self.value())
		return queryset


class OtherProductImagesInlineFormSet(BaseInlineFormSet):
	def get_queryset(self):
		qs = super(OtherProductImagesInlineFormSet, self).get_queryset()
		return qs.only('image').order_by('id')[1:]


class ProductImagesInlineAdmin(admin.TabularInline):
	model = ProductImage
	formset = OtherProductImagesInlineFormSet
	extra = 0
	classes = ('collapse',)
	formfield_overrides = {ImageField: {'widget': ImageWidget}}
	verbose_name_plural = 'ДРУГИЕ ФОТО'


class MainProductImageWidget(ImageWidget):
	width=450
	height=450


class ProductAdminForm(forms.ModelForm):
	main_image = forms.ImageField(allow_empty_file=True, required=False, label='Фото',
		widget=MainProductImageWidget)

	class Meta:
		model = Product
		fields = '__all__'

	def __init__(self, *args, **kwargs):
		super(ProductAdminForm, self).__init__(*args, **kwargs)
		instance = kwargs.get("instance")
		if instance and instance.pk:
			f = instance.images.only('image').first()
			if f:
				self.fields['main_image'].initial = f.image
		else:
			self.fields['shop'].initial = self.fields['shop'].queryset.first()


class MyNumericRangeFilter(RangeNumericFilter):
	template = 'admin/filter_numeric_range.html'


@admin.register(Product)
class ProductAdmin(NumericFilterModelAdmin, ShortDescriptionListFieldMixin):
	list_display = ('title','main_image', 'id', 'amount', 'price', 'active', 'shop', 'short_description')
	fieldsets = ((None, {'fields':('id', 'shop', 'title', 'description', 'active', 'amount', 'price')}),
		('КАТЕГОРИИ', {'fields': ('categories',), 'classes': ('collapse',)}),
		('ОСНОВНОЕ ФОТО', {'fields': ('main_image',)}),
		)
	search_fields = ('id', 'title')
	list_filter = ('active',('price',MyNumericRangeFilter), 
		ShopFilter, CategoryFilter)
	readonly_fields = ('id',)
	filter_horizontal = ('categories',)
	form = ProductAdminForm
	inlines = (ProductImagesInlineAdmin,)
	actions = ('make_active', 'make_inactive')
	list_per_page = 50

	class Media:
		css = {'all': ('css/productlist.css',)}

	def main_image(self, instance):
		url = instance.images.only('image').first()
		if url:
			return format_html("<img src='{}{}' width=100 height=100 style='object-fit:contain' />",
				settings.MEDIA_URL, url.image)
		else:
			return format_html("<img alt='—' />")

	main_image.short_description = 'Фото'

	def formfield_for_manytomany(self, db_field, request, **kwargs):
		if db_field.name == "categories":
			kwargs["queryset"] = Category.objects.only('title').order_by('title')
		return super().formfield_for_manytomany(db_field, request, **kwargs)

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == 'shop':
			qs = None
			if not request.user.is_superuser:
				qs = request.user.managed_shops
			else:
				qs = Shop.objects
			kwargs['queryset']=qs.only('title').order_by('title')
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

	def save_formset(self, request, form, formset, change):
		main_image = form.fields['main_image']
		new_image = form.cleaned_data.get('main_image')
		if main_image.has_changed(main_image.initial, new_image):
			fi = form.instance.images.first()
			if new_image:
				if fi:
					fi.image = new_image
					fi.save()
				else:
					ni = ProductImage(image=new_image, product=form.instance)
					ni.save()
			else:
				if fi:
					fi.delete()
		super(ProductAdmin, self).save_formset(request, form, formset, change)

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		if request.user.is_superuser:
			return qs
		else:
			return qs.filter(shop__id__in=request.user.managed_shops.values_list('id', flat=True))

	def can_access_object(self, request, obj):
		if obj is None:
			return True
		return request.user.managed_shops.filter(id=obj.shop_id).exists()

	def has_view_permission(self, request, obj=None):
		if request.user.is_superuser:
			return True
		else:
			if super().has_view_permission(request, obj):
				return self.can_access_object(request, obj)
			else:
				return False

	def has_change_permission(self, request, obj=None):
		if request.user.is_superuser:
			return True
		else:
			if super().has_change_permission(request, obj):
				return self.can_access_object(request, obj)
			else:
				return False

	def has_delete_permission(self, request, obj=None):
		if request.user.is_superuser:
			return True
		else:
			if super().has_delete_permission(request, obj):
				return self.can_access_object(request, obj)
			else:
				return False

	@admin.action(description='Сделать активными')
	def make_active(self, request, queryset):
		queryset.update(active=True)

	@admin.action(description='Сделать неактивными')
	def make_inactive(self, request, queryset):
		queryset.update(active=False)
