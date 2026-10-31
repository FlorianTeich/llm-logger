from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("proxy", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ModelRoute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_name", models.CharField(max_length=255, unique=True)),
                ("upstream_name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("public_name",)},
        ),
    ]
