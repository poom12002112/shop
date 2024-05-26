# Generated by Django 5.0.1 on 2024-05-24 13:13

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_order_product_counts_order_product_names_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="product_counts",
        ),
        migrations.AlterField(
            model_name="order",
            name="product_names",
            field=models.TextField(blank=True, null=True, verbose_name="商品名稱"),
        ),
    ]
