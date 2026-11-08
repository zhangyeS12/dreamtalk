from pathlib import Path
import io,hashlib,json,zipfile,sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def fingerprint(data):
 with Image.open(io.BytesIO(data)) as im:
  im=im.convert('RGBA');data=bytearray(im.tobytes())
  for offset in range(0,len(data),4):
   if data[offset+3]==0:data[offset:offset+3]=b'\0\0\0'
  return (tuple(im.size),hashlib.sha256(data).hexdigest())
def verify(apk):
 receipt=json.loads((ROOT/'docs/android-brand-assets.json').read_text())
 assert hashlib.sha256((ROOT/receipt['source']).read_bytes()).hexdigest()==receipt['source_sha256'],'Original brand source changed'
 expected={(tuple(x['size']),x['visible_rgba_sha256']) for x in receipt['density_images']}
 with zipfile.ZipFile(apk) as z:
  actual={fingerprint(z.read(n)) for n in z.namelist() if n.startswith('res/') and n.endswith('.png')}
  assert not expected-actual,'Packaged launcher images do not match dreamtalk brand references'
  assert any('dreamtalk-logo.png' in n for n in z.namelist()) or 'lib/arm64-v8a/libdreamtalk_mobile.so' in z.namelist(),'App resources missing'
 return {'density_images':len(receipt['density_images']),'unique_pixel_images':len(expected),'all_packaged':True}
if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]))))
