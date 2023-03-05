import os
import zlib
from hashlib import sha1
import re
from collections import OrderedDict
from pathlib import Path
import magic

"""
* Reading git objects
https://matthew-brett.github.io/curious-git/reading_git_objects.html

* What is the file format of a git commit object data structure?
https://stackoverflow.com/questions/22968856/what-is-the-file-format-of-a-git-commit-object-data-structure

* The Git index file has the following format
https://git-scm.com/docs/index-format
"""

def get_git_dir(from_path=os.getcwd()):
	path = resolve_path(from_path)
	if not os.path.isdir(path) and not os.path.isfile(path):
		return None

	git_dir = None
	if Path(path).is_absolute():
		if path.endswith("/.git"):
			if os.path.isdir(path):
				git_dir = path
		elif "/.git/" in path:
			git_dir = path[:path.index("/.git/")+len("/.git/")]
		elif ".git" in os.listdir(os.getcwd()):
			git_dir = os.path.join(os.getcwd(), ".git")
	elif ".git" in os.listdir(os.getcwd()):
		git_dir = os.path.join(os.getcwd(), ".git")
	
	if git_dir is not None:
		if os.path.isdir(os.path.join(git_dir, "objects")):
			return git_dir
	return None

def get_git_objects_dir(from_path=os.getcwd()):
	git_dir = get_git_dir(from_path)
	if git_dir is not None:
		return os.path.join(git_dir, "objects")
	return None

def is_sha1_hash(value):
	result = re.match('^[a-f0-9]{40}$', value)
	if result:
		return True
	return False
def get_sha1_by_git_object_path(object_path):
	sha1hash_prefix = os.path.basename(Path(object_path).parent.absolute())
	sha1hash_suffix = os.path.basename(object_path)
	sha1hash = "%s%s" % (sha1hash_prefix, sha1hash_suffix)
	if is_sha1_hash(sha1hash):
		return sha1hash
	return None
def get_git_object_path_by_sha1(sha1hash, objects_dir=os.getcwd()):
	if not is_sha1_hash(sha1hash):
		return None
	objects_dir = get_git_objects_dir(objects_dir)
	if objects_dir is None:
		return None
	sha1hash_prefix = sha1hash[:2]
	sha1hash_suffix = sha1hash[2:]

	prefix_dir = os.path.join(objects_dir, sha1hash_prefix)
	if not os.path.isdir(prefix_dir):
		return None
	
	object_path = os.path.join(prefix_dir, sha1hash_suffix)
	if os.path.isfile(object_path):
		return object_path
	return None

def resolve_path(path):
	return str(Path(path).resolve())
def get_relpath(path):
	relpath = path
	if path.startswith(os.getcwd()):
		relpath = path[len(os.getcwd())+1:]
		if len(relpath) == 0:
			relpath = "./"
	return relpath
def file_is_git_object(file_path):
	fullpath = resolve_path(file_path)

	if "/.git/objects/" not in fullpath:
		return False
	if not is_zlib_compressed_file(fullpath):
		return False

	decompressed_content = read_compressed_object(fullpath)
	if decompressed_content is not None:
		git_prefix = get_git_prefix(decompressed_content)
		if git_prefix is not None:
			return True

	return False
def is_zlib_compressed_file(file_path):
	if "zlib compressed data" in get_file_type(file_path):
		return True
	return False
def get_file_type(file_path):
	return magic.from_file(file_path)

def get_full_filepath(file_path):
	return os.path.abspath(file_path)

def extract_git_object_type(decompressed_content):
	if decompressed_content is None:
		return None
	git_prefix = get_git_prefix(decompressed_content)
	object_type, object_size = git_prefix_as_type_size(git_prefix)
	return object_type

def extract_git_object(object_path):
	git_object = extract_git_object_info(object_path)
	if git_object is None:
		return None
	
	decompressed_content = git_object["raw"]

	if git_object["type"] == "tree":
		return extract_git_tree_object(object_path)
	elif git_object["type"] == "blob":
		return extract_git_blob_object(object_path)
	elif git_object["type"] == "commit":
		return extract_git_commit_object(object_path)

	return git_object

def extract_git_object_info(object_path):
	git_object = OrderedDict()
	
	decompressed_content = read_compressed_object(object_path)
	if decompressed_content is None:
		return None
	git_object["sha1"] = get_sha1_by_git_object_path(object_path)
	git_object["raw"] = decompressed_content

	git_prefix = get_git_prefix(decompressed_content)
	object_type, object_size = git_prefix_as_type_size(git_prefix)
	git_object["type"] = object_type
	git_object["size"] = object_size

	return git_object

def extract_git_blob_object(object_file):
	git_object = extract_git_object_info(object_file)
	if git_object is None:
		return None

	if git_object["type"] != "blob":
		return git_object

	git_object["content"] = b'\x00'.join(git_object["raw"].split(b"\x00")[1:]).decode()
	return git_object

def extract_git_commit_object(object_file):
	git_object = extract_git_object_info(object_file)
	if git_object is None:
		return None

	if git_object["type"] != "commit":
		return git_object
	
	git_object["content"] = b'\n'.join(git_object["raw"].split(b"\x00")[1:]).decode()
	return git_object
def extract_git_tree_object(object_file):
	git_object = extract_git_object_info(object_file)
	if git_object is None:
		return None

	if git_object["type"] != "tree":
		return git_object

	git_object["items"] = []
	object_dirs = get_git_objects_dir(object_file)
	
	raw_content = b'\x00'.join(git_object["raw"].split(b"\x00")[1:])

	match_result = re.finditer(b'(\d\d\d\d\d\d? )', raw_content)
	if not match_result:
		return git_object
	
	results = list(match_result)
	if len(results) == 0:
		return git_object

	for i in range(len(results)):
		start_pos = results[i].span()[0]
		if i >= len(results)-1:
			end_pos = len(raw_content)
		else:
			end_pos = results[i+1].span()[0]
		data = raw_content[start_pos:end_pos]

		# // extract tree object (item) information
		item_perm = data.split(b" ")[0].decode()
		if len(item_perm) == 5:
			item_perm = "0%s" % item_perm
		after_perm = b" ".join(data.split(b" ")[1:])
		item_name = after_perm.split(b"\x00")[0].decode()
		item_hash = b"\x00".join(after_perm.split(b"\x00")[1:]).hex()
		
		tree_item_path = get_git_object_path_by_sha1(item_hash, object_dirs)
		blob_object = extract_git_object_info(tree_item_path)
		item_object_type = blob_object["type"]

		git_object["items"].append("%s %s %s    %s" % (item_perm, item_object_type, item_hash, item_name))

	return git_object
def get_object_type(decompressed_content):
	git_prefix = get_git_prefix(decompressed_content)
	if " " in git_prefix:
		return git_prefix.split(" ")[0]
	return None
def git_prefix_as_type_size(git_prefix):
	if " " in git_prefix:
		return git_prefix.split(" ")[:2]
	return None, None

def get_git_prefix(decompressed_content):
	try:
		git_prefix = re.search(b'^[^\x00]+', decompressed_content)
		if git_prefix:
			return git_prefix.group(0).decode()
	except Exception as e:
		print("Exception: %s" % e)
		return None

def get_head_ref():
	git_dir = get_git_dir()
	if git_dir is None:
		return None
	
	head_filepath = os.path.join(git_dir, "HEAD")
	if not os.path.isfile(head_filepath):
		return None
	head_ref = read_file(head_filepath)[0].strip().split(" ")[1]
	return head_ref
def get_head_branch():
	head_ref = get_head_ref()
	if head_ref is None:
		return None

	if "refs/heads/" in head_ref:
		return head_ref[len("refs/heads/"):]
	return head_ref
def get_ref_from_head():
	git_dir = get_git_dir()
	if git_dir is None:
		return None
	
	head_filepath = os.path.join(git_dir, "HEAD")
	if not os.path.isfile(head_filepath):
		return None
	head_ref = read_file(head_filepath)[0].strip().split(" ")[1]
	ref_path = os.path.join(git_dir, head_ref)
	if not os.path.isfile(ref_path):
		return None
	object_ref = read_file(ref_path)[0].strip()
	return object_ref
	

def read_compressed_object(file_path):
	try:
		compressed_contents = open(file_path, 'rb').read()
		decompressed_content = zlib.decompress(compressed_contents)
		return decompressed_content
	except Exception as e:
		print("Exception: %s" % e)
		return None

def read_file(filepath):
    data = None
    with open(filepath, "r") as f:
        data = f.readlines()
    return data