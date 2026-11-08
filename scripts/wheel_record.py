import base64,csv,hashlib,io,zipfile
def write_record(bundle,info):
 rows=[]
 for name in bundle.namelist():
  if name==info+"/RECORD":continue
  data=bundle.read(name)
  digest=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
  rows.append((name,"sha256="+digest,str(len(data))))
 rows.append((info+"/RECORD","",""))
 out=io.StringIO(newline="");csv.writer(out,lineterminator="\n").writerows(rows)
 bundle.writestr(info+"/RECORD",out.getvalue())
