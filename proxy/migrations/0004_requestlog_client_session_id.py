from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("proxy", "0003_modelroute_upstream_base_url")]

    operations = [
        migrations.AddField(
            model_name="requestlog",
            name="client_session_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
    ]
