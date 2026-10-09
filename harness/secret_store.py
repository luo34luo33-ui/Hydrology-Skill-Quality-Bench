"""Windows user-scoped DPAPI secret storage, never plaintext on disk."""
import ctypes
from ctypes import wintypes
import getpass
import os
from pathlib import Path

class Blob(ctypes.Structure):
    _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]

def transform(data,encrypt):
    if os.name!='nt':raise RuntimeError('Windows DPAPI is required')
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.windll.crypt32
    if encrypt:ok=crypt.CryptProtectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:ok=crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    if not ok:raise ctypes.WinError()
    try:return ctypes.string_at(target.pbData,target.cbData)
    finally:ctypes.windll.kernel32.LocalFree(target.pbData)

def read_secret(path):return transform(Path(path).read_bytes(),False).decode('utf-8')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('path');args=p.parse_args()
    value=getpass.getpass('DeepSeek API credential (not logged): ').strip()
    if not value.startswith('sk-'):raise ValueError('Unexpected credential format')
    path=Path(args.path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(transform(value.encode('utf-8'),True))
    print('User-scoped encrypted credential saved.')
