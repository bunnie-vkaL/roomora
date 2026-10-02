from django.db import migrations, models


def require_new_survey(apps, schema_editor):
    # Keep legacy answers for audit, but require fresh A1-F2 answers to publish.
    Profile = apps.get_model("core", "Profile")
    Profile.objects.filter(is_published=True).update(is_published=False)


class Migration(migrations.Migration):
    dependencies = [("core", "0004_profile_avatar")]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="questionnaire_version",
            field=models.CharField(default="2026.2", max_length=20),
        ),
        migrations.RunPython(require_new_survey, migrations.RunPython.noop),
    ]
