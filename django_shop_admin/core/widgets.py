from django import forms

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