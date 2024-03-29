# Generated by Django 3.2.6 on 2021-08-14 13:34

import core.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_auto_20210813_1502'),
    ]

    operations = [
        migrations.AlterField(
            model_name='categoryparent',
            name='to_category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='from_category', to='core.category', verbose_name='Родительская категория'),
        ),
        migrations.AlterField(
            model_name='shop',
            name='imageUrl',
            field=models.ImageField(blank=True, null=True, unique=True, upload_to=core.models.shop_image_path_handler, verbose_name='Фото'),
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(unique=True, upload_to=core.models.product_image_path_handler, verbose_name='Фото')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='core.product', verbose_name='Продукт')),
            ],
            options={
                'verbose_name': 'Фото продукта',
                'db_table': 'productimages',
            },
        ),
    ]
