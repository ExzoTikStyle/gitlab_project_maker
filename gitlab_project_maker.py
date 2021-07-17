#!/usr/bin/env python3
from __future__ import unicode_literals, print_function
import logging
import os
import sys
from argparse import ArgumentParser
from distutils.util import strtobool
import gitlab
from gitlab import GitlabAuthenticationError, GitlabError, GitlabGetError, GitlabCreateError, GitlabUpdateError

### Переменные окружения для работы скрипта
# Адрес gitlab
GITLAB_URL = os.getenv('GITLAB_URL', 'http://gitlab-url')

# Сгенерированный токен
GITLAB_ACCESS_TOKEN = os.getenv('GITLAB_ACCESS_TOKEN', 'token') 

# Ветки для создания
GITLAB_DEFAULT_BRANCHES = [project.strip() for project in os.getenv('GITLAB_DEFAULT_BRANCHES', 'develop,support,release').split(',')] 

# Дефолтная ветка
GITLAB_DEFAULT_BRANCH = os.getenv('GITLAB_DEFAULT_BRANCH', 'develop')

# Дефолтные параметры для репозиториев (Pipelines must succeed)
GITLAB_ONLY_ALLOW_MERGE_IF_PIPELINE_SUCCEEDS = bool(strtobool(os.getenv('GITLAB_ONLY_ALLOW_MERGE_IF_PIPELINE_SUCCEEDS', 'False')))

# Базовая инициализация
GITLAB_INITIALIZE_WITH_README = bool(strtobool(os.getenv('GITLAB_INITIALIZE_WITH_README', 'True'))) 

# Количество апрувов для MR
GITLAB_APPROVALS_BEFORE_MERGE = int(os.getenv('GITLAB_APPROVALS_BEFORE_MERGE', 1)) 

# regxp имён бранчей
GITLAB_BRANCH_NAME_REGEX = os.getenv('GITLAB_BRANCH_NAME_REGEX', '') 

# All discussions must be resolved
GITLAB_ONLY_ALLOW_MERGE_IF_ALL_DISCUSSIONS_ARE_RESOLVED = bool(strtobool(os.getenv('GITLAB_ONLY_ALLOW_MERGE_IF_ALL_DISCUSSIONS_ARE_RESOLVED', 'True')))

###########################################
logger = logging.getLogger(__name__)
non_url_safe = [
    '"', '#', '$', '%', '&', '+', ',', '/', ':', ';', '=', '?', '@', '[', '\\', ']', '^', '`', '{', '|', '}', '~', "'"
]
translate_table = {ord(char): u'' for char in non_url_safe}

def slugify(text):
    text = text.translate(translate_table)
    text = u'_'.join(text.split())
    return text

class prepare_group(object):

    def __init__(self):
        self.logger = logger.getChild(self.__class__.__name__)
        self.parser = ArgumentParser()
        self.add_arguments()

    def add_arguments(self):
        self.parser.add_argument('-u', '--url', action='store', type=str, default=GITLAB_URL, help='URL for GitLab accessing')
        self.parser.add_argument('-t', '--token', action='store', type=str, default=GITLAB_ACCESS_TOKEN, help='Access token for GitLab')
        self.parser.add_argument('-g', '--group', action='store', type=str, required=True, help='Searching group name')
        self.parser.add_argument('-c', '--create-group', action='store_true', help='Create group if not exist')
        self.parser.add_argument('-p', '--projects', nargs='+', type=str, required=True, help='Created projects')
        self.parser.add_argument('--branches', nargs='+', type=str, default=GITLAB_DEFAULT_BRANCHES, help='Created branches')
        self.parser.add_argument('-b', '--branch', action='store', type=str, default=GITLAB_DEFAULT_BRANCH, help='Default branch')
        self.parser.add_argument('--branch_name_regex', action='store', type=str, default=GITLAB_BRANCH_NAME_REGEX, help='Branch RegExp')
        self.parser.add_argument('--only-allow-merge-if-pipeline-succeeds', action='store_true',default=GITLAB_ONLY_ALLOW_MERGE_IF_PIPELINE_SUCCEEDS)
        self.parser.add_argument('--initialize-with-readme', action='store_true', default=GITLAB_INITIALIZE_WITH_README)
        self.parser.add_argument('--approvals-before-merge', action='store', type=int, default=GITLAB_APPROVALS_BEFORE_MERGE)
        self.parser.add_argument('--only-allow-merge-if-all-discussions-are-resolved', action='store_true',default=GITLAB_ONLY_ALLOW_MERGE_IF_ALL_DISCUSSIONS_ARE_RESOLVED)
        self.parser.add_argument('--deny_delete_tag', action='store_true', default='True')
        self.parser.add_argument('--author_email_regex', action='store', type=str, default='@esphere.ru$')
        self.parser.add_argument('-d', '--debug', action='store_true', help='Debug mode')

    def auth(self, url, token):
        try:
            self.logger.info('Подключение к %s', url)
            self.api = gitlab.Gitlab(url, token)
            self.api.auth()
            return True
        except GitlabAuthenticationError:
            self.logger.error('Невалидный токен')
        except Exception as e:
            self.logger.debug(e)

    def get_group(self, group_name, create=False):
        assert self.api, 'Неавторизованный в api токен'
        try:
            if group_name:
                self.logger.info('Поиск группы %s', group_name)
                groups = self.api.groups.list(search=group_name)
                if not groups and create:
                    self.logger.info('Создание группы %s', group_name)
                    return self.api.groups.create(dict(name=group_name, path=slugify(group_name)))
                elif groups:
                    return groups[0]
        except GitlabCreateError as e:
            self.logger.error('Ошибка создания группы: %s', e.error_message)
        except Exception as e:
            self.logger.debug(e)

    def create_projects(self, projects_list, group, options, **project_attrs):
        try:
            self.logger.info('Поиск проекта %s в группе %s', projects_list, group.name)
            projects = []
            for project in projects_list:
                try:
                    projects.append(self.api.projects.get('/'.join((group.path, project))))
                except GitlabGetError:
                    pass
            exists_projects_names = []
            mandatory_attrs, optional_attrs = self.api.projects.get_update_attrs()
            for project in projects:
                exists_projects_names.append(project.name)
                update_answer = ''
                while len(update_answer) != 1 or update_answer not in ('Y', 'N'):
                    print('Проект {} уже существует, перезаписать параметры? (Y/n):'.format(
                        '/'.join((group.path, project.name))
                    ))
                    update_answer = input().upper()
                if update_answer != 'N':
                    self.logger.info('Обнеовление параметров проекта %s', project.name)
                    for attr, value in project_attrs.items():
                        if attr in mandatory_attrs or attr in optional_attrs:
                            setattr(project, attr, value)
                    project.save()
                    # Установка настроек проекта
                    self.set_project_settings(project, options)
            for project in projects_list:
                if project not in exists_projects_names:
                    self.logger.info('Создание проекта %s в группе %s', project, group.name)
                    repo = self.api.projects.create(dict(name=project, namespace_id=group.id, **project_attrs))
                    # Установка настроек проекта
                    self.set_project_settings(repo, options)
                    projects.append(repo)
            return projects
        except GitlabCreateError as e:
            self.logger.error('Ошика создания проекта: %s', e.error_message)
        except GitlabUpdateError as e:
            self.logger.error('Ошибка обновления проекта: %s', e.error_message)
        except Exception as e:
            self.logger.debug(e)

    def set_project_settings(self, project, options):
        for branch in options.branches:
            self.logger.info('Поиск или создание ветки %s для проекта %s', branch, project.name)
            try:
                project.branches.get(branch)
            except GitlabGetError:
                project.branches.create(dict(branch=branch, ref='master'))
        try:
            self.logger.info('Установка дефолтной ветки %s для проекта %s', options.branch, project.name)
            project.default_branch = options.branch
            project.save()
        except:
            pass
        try:
            self.logger.info('Настройка push rules для проекта  %s', project.name)
            push_rules = project.pushrules.get()
            push_rules.author_email_regex = options.author_email_regex
            push_rules.deny_delete_tag = options.deny_delete_tag
            push_rules.branch_name_regex = options.branch_name_regex
            push_rules.save()
        except GitlabGetError:
            self.logger.info('Создание push rules для проекта %s', project.name)
            try:
                project.pushrules.create(dict(
                    author_email_regex=options.author_email_regex,
                    deny_delete_tag=options.deny_delete_tag,
                    branch_name_regex = options.branch_name_regex
                ))
            except GitlabCreateError as e:
                self.logger.info('Ошибка создания push rules: %s', e.error_message)
            except Exception as e:
                self.logger.debug(e)
        except GitlabError as e:
            self.logger.error('Ошибка настройки push rules: %s', e.error_message)
        except Exception as e:
            self.logger.debug(e)
        protected_branches = project.protectedbranches.list()
        if not protected_branches:
            self.logger.info('Настройка защищённых веток для проекта %s', project.name)
            for branch in options.branches:
                project.protectedbranches.create(dict(
                    name=branch,
                    merge_access_level=gitlab.DEVELOPER_ACCESS,
                    push_access_level=gitlab.MAINTAINER_ACCESS
                ))
            project.protectedbranches.create(dict(
                name='master',
                merge_access_level=gitlab.MAINTAINER_ACCESS,
                push_access_level=gitlab.MAINTAINER_ACCESS
            ))

    def run(self):
        self.logger.debug(sys.argv)
        options = self.parser.parse_args()
        logging.basicConfig(level=options.debug and logging.DEBUG or logging.INFO, format='%(levelname)s: %(message)s')
        self.logger.debug(options)
        # Подключение к API
        if not self.auth(options.url, options.token):
            return
        if options.debug:
            self.api.enable_debug()
        # Получение группы
        group = self.get_group(options.group, options.create_group)
        if not group:
            self.logger.info('Группа "%s" не найдена', options.group)
            return
        self.logger.debug(group)
        # Создание проектов
        projects = self.create_projects(
            options.projects,
            group,
            options,
            only_allow_merge_if_pipeline_succeeds=options.only_allow_merge_if_pipeline_succeeds,
            only_allow_merge_if_all_discussions_are_resolved=options.only_allow_merge_if_all_discussions_are_resolved,
            approvals_before_merge=options.approvals_before_merge,
            initialize_with_readme=options.initialize_with_readme
        )
        self.logger.debug(projects)
        self.logger.info('Успешно завершено')


if __name__ == '__main__':
    prepare_group().run()
