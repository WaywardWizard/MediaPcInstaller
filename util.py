import subprocess
import re
from collections import defaultdict as dd
import urllib
import pathlib

PIPE='|'
def bash(cmd, check=True):
    
    commands=[[]]
    for e in cmd:
        if e==PIPE:
            commands.append([])
        commands[-1].append(e)

    results=[[]]
    stdin=None
    for c in commands:
        result=subprocess.run(
            cmd.split(),
            stdin=stdin,
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
    bytesize=int(resp.getheader('contentlength'))
    _, col = bash('stty size').stdout.split()
    with open(target,'wb') as file:
        while not resp.closed:
            file.write(resp.read())
            if showProgress:
                done=file.tell()
                pct=done/bytesize
                bar='#'*int(col*pct)
                print('{: <4.1%} ||{}|| {}[Mibi]'.format(pct,bar,(done/pow(2,20))),end='\r')
        file.write(resp.read())
        
    return(resp.closed)
