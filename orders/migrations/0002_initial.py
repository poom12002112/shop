# Generated by Django 5.0.1 on 2024-03-27 16:32

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("orders", "0001_initial"),
        ("products", "0003_relationalproduct"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="product",
            field=models.ManyToManyField(
                related_name="order_set",
                through="products.RelationalProduct",
                to="products.product",
            ),
        ),
    ]
