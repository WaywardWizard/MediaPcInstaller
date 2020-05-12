import subprocess
import re
from collections import defaultdict as dd
import urllib.request
import pathlib
import shutil

PIPE='|'
def bash(cmd:str, viashell=False, check:bool=True):
    """Run a command and check its return status
    
    :cmd 
    :param bool check: When true, throw and exception for failed command
    """
    
    if __debug__:
        print(f'bash {cmd}')

    commands=[[]]
    for e in cmd.split():
        if e==PIPE:
            commands.append([])
            continue
        commands[-1].append(e)

    results=[]
    stdin=None

    for c in commands:
        if viashell:
            c=' '.join(c)
        result=subprocess.run(
            c,
            input=stdin,
            shell=viashell,
            capture_output=True,
            check=check,
        )
        results.append(result)
        if(result.returncode!=0):
            break
        stdin=result.stdout
    
    results[-1].stdout=results[-1].stdout.decode()
    return(results[-1])
    
def getDictionaryFromKeyValueString(string):
    d=dd(lambda :None)
    for line in string.splitlines():
        kv=line.split('=')
        d[kv[0]]=kv[1]
    return(d)

def userConfirm(prompt):
    while re.fullmatch(r'y',input(prompt),re.IGNORECASE) is None:
        continue
    
def dlFile(url, target:pathlib.Path, showProgress=True):
    resp=urllib.request.urlopen(url)
    h=resp.getheaders()
    #bytesize=int(resp.getheader('content-length'))
    col, _= shutil.get_terminal_size()
    with open(pathlib.Path(target,'fn'),'wb') as imageFile:
        while not resp.closed:
            imageFile.write(resp.read())
            if showProgress:
                done=imageFile.tell()
                pct=done
                bar='#'*int(col*pct)
                print('{: <4.1%} ||{}|| {}[Mibi]'.format(pct,bar,(done/pow(2,20))),end='\r')
        imageFile.write(resp.read())
        
    return(resp.closed)
