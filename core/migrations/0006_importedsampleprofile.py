from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0005_lifestyle_survey_2026_2")]

    operations = [
        migrations.CreateModel(
            name="ImportedSampleProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_id", models.CharField(max_length=20, unique=True)),
                ("source_data", models.JSONField(default=dict)),
                ("imported_at", models.DateTimeField(auto_now=True)),
                ("profile", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sample_source", to="core.profile")),
            ],
        ),
    ]
