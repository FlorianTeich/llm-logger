from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("proxy", "0002_modelroute")]

    operations = [
        migrations.AddField(
            model_name="modelroute",
            name="upstream_base_url",
            field=models.URLField(blank=True),
        ),
    ]
