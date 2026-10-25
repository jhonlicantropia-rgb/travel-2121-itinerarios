"""Build ordinary, independently readable HTML pages from bounded GitHub blobs."""
import base64,gzip,hashlib,json,re,shutil,sys
from pathlib import Path

DATA_URI=re.compile(r'data:(image/(?:jpeg|png|webp|svg\+xml)|font/(?:woff2?|ttf));base64,([A-Za-z0-9+/=]+)',re.I)
EXTENSIONS={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/svg+xml':'svg','font/woff2':'woff2','font/woff':'woff','font/ttf':'ttf'}

def restore_bundle(value):
    if value.get('version')!=1 or not re.fullmatch(r'__TRAVEL2121_ASSET_[a-f0-9]{16}_+',value.get('prefix','')) or not isinstance(value.get('assets'),list) or len(value['assets'])>500 or not isinstance(value.get('html'),str):
        raise ValueError('Invalid public document bundle')
    assets=value['assets']
    if not all(isinstance(v,str) and DATA_URI.fullmatch(v) for v in assets):raise ValueError('Invalid document asset')
    def replace(match):
        index=int(match[1])
        if index>=len(assets):raise ValueError('Missing document asset')
        return assets[index]
    return re.sub(re.escape(value['prefix'])+r'(\d+)__',replace,value['html'])

def decode_document(index,directory):
    text=index.decode('utf-8');match=re.search(r'const config=(\{.*?\});document',text)
    if not match:return text
    config=json.loads(match[1]);files=config.get('files')
    if not isinstance(files,list) or len(files)>400:raise ValueError('Invalid payload list')
    if files:
        pieces=[]
        for name in files:
            if not re.fullmatch(r'payload-v[234]-[a-f0-9]{64}-\d+\.txt',name):raise ValueError('Invalid payload name')
            part=(directory/name).read_text()
            if len(part)>49152 or not re.fullmatch(r'[A-Za-z0-9+/]*={0,2}',part):raise ValueError('Invalid payload part')
            pieces.append(part)
        encoded=''.join(pieces)
    else:encoded=config.get('data','')
    if not isinstance(encoded,str) or len(encoded)>20*1024*1024:raise ValueError('Invalid payload size')
    data=gzip.decompress(base64.b64decode(encoded,validate=True))
    if len(data)>12*1024*1024+256:raise ValueError('Document too large')
    decoded=data.decode('utf-8');html=restore_bundle(json.loads(decoded)) if config.get('format')=='travel2121-bundle-v1' else decoded
    if hashlib.sha256(html.encode()).hexdigest()!=config.get('hash'):raise ValueError('Document integrity mismatch')
    return html

def externalize_assets(html,directory):
    media=directory/'media';written={}
    def replace(match):
        value=match[0]
        if value not in written:
            data=base64.b64decode(match[2],validate=True);name=hashlib.sha256(data).hexdigest()+'.'+EXTENSIONS[match[1].lower()]
            media.mkdir(exist_ok=True);(media/name).write_bytes(data);written[value]='media/'+name
        return written[value]
    html=DATA_URI.sub(replace,html)
    def image(match):
        tag=match[0]
        if not re.search(r'\bdecoding\s*=',tag):tag=tag[:-1]+' decoding="async">'
        if not re.search(r'\bloading\s*=',tag) and not re.search(r'hero-image|cover-photo|agency-logo|brand-mark',tag):tag=tag[:-1]+' loading="lazy">'
        return tag
    return re.sub(r'<img\b[^>]*>',image,html,flags=re.I),len(written)

def build(source,destination):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve() or source.resolve() in destination.resolve().parents:raise ValueError('Output must be outside source')
    shutil.copytree(source,destination,dirs_exist_ok=True)
    count=0;assets=0;html_bytes=0
    for file in sorted((source/'viajes').glob('*/index.html')):
        index=file.read_bytes();revision=hashlib.sha1(('blob '+str(len(index))+'\0').encode()+index).hexdigest()
        html=decode_document(index,file.parent)
        if not re.match(r'<!doctype html>',html,re.I) or '</html>' not in html:raise ValueError('Incomplete public HTML')
        output=destination/file.relative_to(source);html,total=externalize_assets(html,output.parent)
        html+='\n<!-- travel2121-rendered:'+revision+' -->\n';output.write_text(html,encoding='utf-8');count+=1;assets+=total;html_bytes+=len(html.encode())
    return {'documents':count,'assets':assets,'html_bytes':html_bytes}

if __name__=='__main__':
    print(json.dumps(build(sys.argv[1],sys.argv[2])))
