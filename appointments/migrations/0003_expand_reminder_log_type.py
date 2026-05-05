from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0002_architecture_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointmentreminderlog",
            name="reminder_type",
            field=models.CharField(
                help_text="Reminder identifier, e.g. reminder_1_days or reminder_2_hours.",
                max_length=50,
            ),
        ),
    ]
