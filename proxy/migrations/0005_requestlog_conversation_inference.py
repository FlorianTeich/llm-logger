from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("proxy", "0004_requestlog_client_session_id")]

    operations = [
        migrations.AddField(
            model_name="requestlog",
            name="client_scope_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="requestlog",
            name="message_fingerprints",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="requestlog",
            name="conversation_group_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="requestlog",
            name="conversation_group_source",
            field=models.CharField(
                blank=True,
                choices=[("header", "Explicit session ID"), ("inferred", "Inferred from history")],
                max_length=16,
            ),
        ),
    ]
