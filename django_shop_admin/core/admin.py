from django.contrib import admin
from django.contrib.admin.widgets import AdminFileWidget, FilteredSelectMultiple
from django.utils.safestring import mark_safe
from .models import Shop, Category, Product
from django.db.models import ImageField, Q
from django import forms
from admin_numeric_filter.admin import RangeNumericFilter, NumericFilterModelAdmin
from django.utils.html import format_html
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.db import transaction
from django.contrib.admin.options import (
	PermissionDenied, unquote, DisallowedModelAdminToField,
	flatten_fieldsets, all_valid, IS_POPUP_VAR, TO_FIELD_VAR, 
	helpers, _
)

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
	list_display = ('title','id')
	fields = ('id', 'title', 'description', 'imageUrl')
	search_fields = ('title',)
	ordering = ('title',)
	readonly_fields = ('id',)
	formfield_overrides = {ImageField: {'widget': AdminImageWidget}}


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
	parents = forms.ModelMultipleChoiceField(
				queryset = Category.objects.only('title').order_by('title'),
				required=False,
				widget=FilteredSelectMultiple(
						verbose_name='Родительские категории',
						is_stacked=False
					))

	children = forms.ModelMultipleChoiceField(
				queryset=Category.objects.only('title').order_by('title'),
				required=False,
				widget=FilteredSelectMultiple(
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
class CategoryAdmin(admin.ModelAdmin):
	list_display = ('title','id','category_actions')
	search_fields = ('products__id', 'title')
	list_filter = (ParentCategoryFilter,)
	ordering = ('title',)
	readonly_fields = ('id',)
	form = CategoryAdminForm

	change_form_template = 'admin/category_change_form.html'

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
			readonly_fields = flatten_fieldsets(fieldsets)
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
		objs = Shop.objects.filter(products__isnull=False).only('title').distinct().order_by('title')
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
		objs = Category.objects.filter(products__isnull=False).only('title').distinct().order_by('title')
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
	fields = ('id', 'active', 'title', 'description', 'amount', 'price', 'categories', 'shop')
	search_fields = ('id', 'title')
	list_filter = ('active',('price',MyNumericRangeFilter), 
		ShopFilter, CategoryFilter)
	readonly_fields = ('id',)
	filter_horizontal = ('categories',)

	def formfield_for_manytomany(self, db_field, request, **kwargs):
		if db_field.name == "categories":
			kwargs["queryset"] = Category.objects.only('title').order_by('title')
		return super().formfield_for_manytomany(db_field, request, **kwargs)

