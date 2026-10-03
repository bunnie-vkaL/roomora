from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_importedsampleprofile")]

    operations = [
        migrations.AddField(
            model_name="importedsampleprofile",
            name="estimated_answers",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="importedsampleprofile",
            name="behavior_metrics",
            field=models.JSONField(default=dict),
        ),
    ]
