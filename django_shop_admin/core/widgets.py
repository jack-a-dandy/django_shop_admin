from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.html import conditional_escape
from django.utils.html import format_html

class ImageWidget(forms.widgets.ClearableFileInput):
	template_name = "widgets/image_field.html"
	clear_checkbox_label = ' Удалить?'
	width = 300
	height = 300
	object_fit = 'contain'

	class Media:
		js = ('js/shownewimage.js',)

	def get_context(self, name, value, attrs):
		context = super(ImageWidget, self).get_context(name, value, attrs)
		context['widget'].update({
			'width': self.width,
			'height': self.height,
			'object_fit': self.object_fit
			})
		return context


class FilteredSelectMultipleWithReadonlyMode(FilteredSelectMultiple):
	def render(self, name, value, attrs=None, renderer=None):
		if self.attrs.get('is_readonly'):
			return format_html("<div class='readonly'>{}</div>", 
				conditional_escape(", ".join(value)))
		else:
			return super(FilteredSelectMultipleWithReadonlyMode,self).render(name,value,attrs,renderer)