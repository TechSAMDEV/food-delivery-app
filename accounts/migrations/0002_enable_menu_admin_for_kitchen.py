from django.db import migrations


def enable_menu_admin_access(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role__in=['KITCHEN', 'ADMIN']).update(is_staff=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(enable_menu_admin_access, migrations.RunPython.noop),
    ]
