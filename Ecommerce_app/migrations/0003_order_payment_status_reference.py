from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('Ecommerce_app', '0002_order_orderitem')]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')],
                default='pending', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_reference',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
