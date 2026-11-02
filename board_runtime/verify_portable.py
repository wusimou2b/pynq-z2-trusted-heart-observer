"""Verify portable demo files without hardware access. Run from any cwd."""
import hashlib,json,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
def verify():
 d=json.loads((ROOT/'portable-manifest.json').read_bytes())
 for name,record in d['files'].items():
  rel=PurePosixPath(name);p=ROOT/name
  if rel.is_absolute() or '..' in rel.parts or ':' in name or '\\' in name:raise ValueError('unsafe member')
  if p.is_symlink() or not p.resolve(strict=True).is_relative_to(ROOT):raise ValueError('escaped member')
  b=p.read_bytes()
  if record['kind']=='notebook-source':
   n=json.loads(b);k=n['metadata']['kernelspec']
   b=json.dumps([n['nbformat'],k['name'],k['language'],[(c['cell_type'],''.join(c['source'])) for c in n['cells']]],ensure_ascii=False,separators=(',',':')).encode()
  if hashlib.sha256(b).hexdigest()!=record['sha256']:raise ValueError('member differs: '+name)
 runtime=ROOT/'runtime';sys.path.insert(0,str(runtime))
 from demo_continuous_guard import verify as runtime_verify
 from lean_ps_guard import verify_source
 checked=runtime_verify(d['runtime_manifest_sha256'],runtime)
 source=verify_source(runtime,ROOT/'v3b25 native100 heart video')
 return dict(complete=True,verified_members=len(d['files']),hardware_accessed=False,
             manifest_sha256=d['runtime_manifest_sha256'],native_binary_sha256=source['binary']['sha256'])
if __name__=='__main__':print(json.dumps(verify()))
