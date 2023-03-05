# git-tools

Lets try to dig into git´s inner work without git ;)

## usage

```bash
usage: git-object [-h] [-p] [-t] [-s] [-r] [-v] [--head] [type|object]

Git Helper Tool - File-Object Info

positional arguments:
  type|object  object sha1 or path

options:
  -h, --help   show this help message and exit
  -p           pretty-print <object> content
  -t           show object type (one of 'blob', 'tree', 'commit', 'tag', ...)
  -s           show object size
  -r           Output raw content
  -v           Verbose mode
  --head       get object from head
```
