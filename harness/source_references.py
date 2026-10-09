"""Host-owned source resolution; container paths never become Windows drives."""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from contextvars import ContextVar
from harness.filesystem import filesystem_path

SCORING_VERSION='composite-scientific-v3'
PUBLIC_CONTEXT=ContextVar('frozen_public_sources',default=None)

class SourceReferenceError(ValueError):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)

def canonical(path):
    return Path(filesystem_path(path)).resolve()

def resolve_reference(workspace,base,raw,test_dir=None):
    if not isinstance(raw,str) or not raw:
        raise SourceReferenceError('invalid_source_path','Source path must be a nonempty string')
    posix=PurePosixPath(raw.replace('\\','/'))
    if '..' in posix.parts or PureWindowsPath(raw).drive:
        raise SourceReferenceError('unsafe_source_path','Parent traversal and host absolute paths are forbidden')
    public=None
    if raw.startswith('/public/'):
        record=PUBLIC_CONTEXT.get()
        if record is None and test_dir is not None:
            manifest=canonical(test_dir)/'expected/public_sources.json'
            if manifest.is_file():record=json.loads(manifest.read_text(encoding='utf-8'))
        rel=raw[len('/public/'):]
        if not record or rel not in record.get('files',{}):
            raise SourceReferenceError('unapproved_public_source','Public reference is not in the frozen host manifest')
        root=canonical(record['root']);path=canonical(root/rel)
        public=record['files'][rel]
    else:
        root=canonical(workspace)
        if raw.startswith('/work/'):
            path=canonical(root/raw[len('/work/'):])
        elif posix.is_absolute():
            raise SourceReferenceError('unsafe_source_path','Unknown container absolute path')
        else:path=canonical(canonical(base)/raw)
    try:path.relative_to(root)
    except ValueError as exc:raise SourceReferenceError('unsafe_source_path','Source escapes its allowed root') from exc
    if not path.is_file():raise SourceReferenceError('missing_source','Declared source file is missing')
    if public and hashlib.sha256(path.read_bytes()).hexdigest()!=public:
        raise SourceReferenceError('frozen_public_source_changed','Frozen public source has changed')
    return path

def verify_reference(workspace,base,ref,test_dir=None):
    if not isinstance(ref,dict):raise SourceReferenceError('missing_evidence','Reference must contain path and sha256')
    path=resolve_reference(workspace,base,ref.get('path'),test_dir)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=ref.get('sha256'):
        raise SourceReferenceError('source_hash_mismatch','Declared SHA-256 does not match the source bytes')
    return path
