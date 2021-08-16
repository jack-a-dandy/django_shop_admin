from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from core.permissions import groups_dict


class Command(BaseCommand):
    help = 'Создает группы с указанными правами.'

    def handle(self, *args, **options):
    	for name, permissions in groups_dict.items():
    		print(f" - {name}:")
    		g = Group.objects.get_or_create(name=name)[0]
    		g.permissions.set(Permission.objects.filter(codename__in=permissions))
    		for p in permissions:
    			print(f" {p}")