
# Scripts

Installing requirements:

```
pip3 install -r requirements.txt
```

How to use:

```
python3 gitlab_project_maker.py -g group_name --projects proj1 proj2 
```

Variables:

	    -u gitlab-url
	    -t access-token
	    -g group 
	    -c make group if not exist (default no)
	    --projects backend frontend
	    --branches develop support release
	    --branch develop
	    --branch_name_regex '^((hotfix|feature|bugfix)\/(spranet)-(\d{3,5}|notask)(-[a-z0-9]+)*|develop|master|release(\-v?\d{1,2}\.\d{1,3}\.\d{1,3})?|fork\/[a-zA-Z0-9]+.*)$'
	    --only-allow-merge-if-pipeline-succeeds
	    --only-allow-merge-if-all-discussions-are-resolved
	    --initialize-with-readme
	    --approvals-before-merge 1
	    --deny_delete_tag
	    --author_email_regex @esphere.ru$

