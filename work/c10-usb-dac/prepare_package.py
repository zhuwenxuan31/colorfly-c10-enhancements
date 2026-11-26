"""Offline app-only USB DAC v72 and exact-v70 rollback v73. Never USB."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,zipfile
BASE=Path(__file__).resolve().parent
PROTO=BASE.parent/'c10-prototype'
sys.path.insert(0,str(PROTO));sys.path.insert(0,str(BASE.parent/'c10-dual-timer'))
from package import parse,rebuild
from read_ext import ExtReader
from verify_updater_scope import verify
from prepare_package import inventory
OUT=BASE.parents[1]/'outputs/C10_USB_DAC兼容修复_候选_v72'
ZIP=Path('inputs/20160721_C10固件_update.zip')
TOOLS=PROTO/'fs-tools/e2fsprogs-1.47.2'
def sha(b):return hashlib.sha256(b).hexdigest()
def quote(p):return '"'+str(p).replace('\\','\\\\').replace('"','\\"')+'"'
def main():
    # Use the already extracted original when the user moves the Desktop ZIP.
    # It is tied to the original extraction manifest by a full-container SHA.
    original=(BASE.parent/'c10-analysis/c10_update.bin').read_bytes()
    assert sha(original)=='ba207c08fa29b88bc4d40252cbd9838a5d6fac7d57ea752a2cbb1010e8ce2cc3'
    source=parse(original);manifest=json.loads((BASE/'build/audit.json').read_text())
    candidate=(BASE/'build/g_audio.candidate.ko').read_bytes()
    assert sha(candidate)==manifest['candidate_sha256']
    oldpackage=(BASE.parents[1]/'outputs/C10_EQ实时调节_候选_v70/C10_EQ实时调节_待实测_v70.bin').read_bytes()
    assert sha(oldpackage)=='d3e1d762e202230ebadb07ef66ea3218f4147ded4db2ff4ab518da506f3916f5'
    rollback=parse(oldpackage)['payloads'][3]
    OUT.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix='c10-eq-offline-') as td:
        temp=Path(td);image=temp/'appfs.ext3';image.write_bytes(rollback)
        before=inventory(ExtReader(image));name='local/modules/g_audio.ko'
        assert before[name]['sha256']=='bbb5b13ff89919d9e13f53b954974185e4ae92ad7f737e20528d6a995e428773'
        commands=['rm /'+name,f'write {quote(BASE/"build/g_audio.candidate.ko")} /{name}',
                  f'set_inode_field /{name} mode 0{before[name]["mode"]:o}']
        script=temp/'debugfs.txt';script.write_text('\n'.join(commands)+'\n')
        edit=subprocess.run([str(TOOLS/'debugfs/debugfs'),'-w','-f',str(script),str(image)],capture_output=True,text=True,check=True)
        (OUT/'debugfs.log').write_text(edit.stdout+edit.stderr)
        check=subprocess.run([str(TOOLS/'e2fsck/e2fsck'),'-fn',str(image)],capture_output=True,text=True)
        (OUT/'e2fsck.log').write_text(check.stdout+check.stderr);check.check_returncode()
        assert image.stat().st_size==len(source['payloads'][3])
        reader=ExtReader(image);after=inventory(reader)
        assert set(before)==set(after)
        assert reader.contents(after[name]['inode'])==candidate
        assert after[name]['mode']==before[name]['mode']
        for path in before:
            if path!=name:
                assert all(before[path][key]==after[path][key] for key in ['mode','size','sha256']),(path,before[path],after[path])
        records=[]
        for filename,appfs,version in [('C10_USB_DAC兼容修复_待实测_v72.bin',image.read_bytes(),72),
                                     ('C10_回退已验证实时EQ_v73.bin',rollback,73)]:
            binary=rebuild(original,appfs,version);parsed=parse(binary)
            assert parsed['payloads'][:3]==source['payloads'][:3]
            assert parsed['burn_offsets']==source['burn_offsets']
            assert parsed['order']==4 and parsed['total']==1
            scope=verify(binary);(OUT/filename).write_bytes(binary)
            records.append({'name':filename,'version':version,'sha256':sha(binary),'size':len(binary),'scope':scope})
        assert after['local/aplayer/ap.dge']['sha256']=='beca3dedeef9b191dd6f71e6b72274c8a9b3eb09fbe50266cbb77d640a3fb2ff'
        report={'status':'offline candidate; NOT staged or physically installed',
                'usb_audio_module_sha256':sha(candidate),'app_v70_sha256':after['local/aplayer/ap.dge']['sha256'],'changed_files':[name],'other_files_preserved':len(before)-1,
                'stock_mplayer_sha256':after['local/aplayer/mplayer']['sha256'],
                'rollback_is_exact_v70_application_filesystem':True,'packages':records,
                'v70_realtime_eq_user_confirmed':True,'usb_dac_audio_physically_tested':False}
        (OUT/'候选包核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        (OUT/'补丁明细.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
