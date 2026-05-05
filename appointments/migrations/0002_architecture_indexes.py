from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(fields=["date", "start_time"], name="appt_date_start_idx"),
        ),
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(fields=["status", "date"], name="appt_status_date_idx"),
        ),
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(fields=["customer", "date"], name="appt_customer_date_idx"),
        ),
        migrations.AddIndex(
            model_name="scheduleblock",
            index=models.Index(fields=["date", "start_time"], name="block_date_start_idx"),
        ),
    ]
