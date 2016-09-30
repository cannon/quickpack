import struct
import re
import os
import shlex
import sys
import functools
import itertools

#all $...2 keys work as well
vtf_keys = set(['$basetexture','$detail','$blendmodulatetexture','$bumpmap','$normalmap','$parallaxmap','$heightmap','$selfillummask','$lightwarptexture','$envmap','$displacementmap'])

def main():
    print("\nQuickPack by Jackson Cannon - https://github.com/jackson-c/quickpack")

    if len(sys.argv) < 2:
        print("Usage: "+sys.argv[0]+" path/to/filename.bsp")
        sys.exit()

    pathparts = sys.argv[1].replace("/","\\").split("\\")
    gameroot = '\\'.join(pathparts[0:-2])
    os.chdir(gameroot)
    
    dependencies = {}

    bsp_file = open(sys.argv[1],'rb')

    print("\nReading BSP...")

    entitylump = read_lump(bsp_file, 0)
    texturelump = read_lump(bsp_file, 43)
    staticproplump = read_lump(bsp_file, 35)

    #Find (brush) Materials
    maptextures = texturelump.split(b'\0')[:-1]

    for i in maptextures:
        dependencies[sanitize_filename("materials/"+i.decode("ascii")+".vmt")] = False

    #Find Models
    mapmodels = regex_find(b"models/[a-z0-9_\\- /\\\\]+\\.mdl", staticproplump+b"\0"+entitylump)

    for i in mapmodels:
        dependencies[i] = False

    #Find Sounds
    mapsounds = regex_find(b"[a-z0-9_\\- /\\\\]+\\.wav", entitylump)
    mapsounds = mapsounds.union(regex_find(b"[a-z0-9_\\- /\\\\]+\\.ogg", entitylump))
    mapsounds = mapsounds.union(regex_find(b"[a-z0-9_\\- /\\\\]+\\.mp3", entitylump))

    for i in mapsounds:
        dependencies["sound/"+i] = False

    bsp_file.close()

    print("Finding dependencies...")

    moreitems = True
    while moreitems:
        moreitems = False
        for file, checked in list(dependencies.items()):
            if checked == False:
                newitems,deletethis = check_file(file)
                dependencies[file] = True
                for newitem in newitems:
                    newitem = sanitize_filename(newitem)
                    if not (newitem in dependencies):
                        dependencies[newitem] = False
                        moreitems = True
                if deletethis:
                    del dependencies[file]

    filetypelist = {}
    for file, checked in dependencies.items():
        filetype = file.split(".",1)[-1]
        if filetype in filetypelist:
            filetypelist[filetype] += 1
        else:
            filetypelist[filetype] = 1
            

    print("\nDone. Found custom content:")
    for k,v in filetypelist.items():
        print("    "+str(v)+" "+str(k)+" files.")

    os.chdir("../bin")

    print("\nWriting to "+sys.argv[1]+"...")

    if os.path.isfile("quickpack.txt"):
        os.remove("quickpack.txt")

    outfile = open("quickpack.txt","w")
    for file, checked in dependencies.items():
        outfile.write(file+'\n')
        outfile.write(gameroot+"\\"+(file.replace("/","\\"))+'\n')

    outfile.close()

    bspfilenamecmd = sys.argv[1]
    if ' ' in bspfilenamecmd:
        bspfilenamecmd = '"'+bspfilenamecmd+'"'

    os.system("bspzip.exe -addlist "+bspfilenamecmd+" quickpack.txt "+bspfilenamecmd+" > nul 2>&1")

    print("Done!")

def read_lump(bsp_file, id):
    bsp_file.seek(8 + (id*16))
    fileofs, = struct.unpack('<i', bsp_file.read(4))
    filelen, = struct.unpack('<i', bsp_file.read(4))
    bsp_file.seek(fileofs)
    return bsp_file.read(filelen)

def regex_find(regex, data):
    regex = re.compile(regex,re.IGNORECASE)
    data = re.findall(regex, data)
    data = set(list(map(lambda x: sanitize_filename(x.decode("ascii")), data)))
    return data

def readcstr(f):
    toeof = iter(functools.partial(f.read, 1), '')
    return ''.join(itertools.takewhile('\0'.__ne__, toeof))

def sanitize_filename(file):
    return file.lower().replace("\\","/")

def check_file(file):
    filebase = file.split(".",1)[0]
    filetype = file.split(".",1)[-1]
    depends = []
    deletethis = False

    #if file doesn't exist, we assume it's in a vpk so no need to pack
    if os.path.isfile(file):
        size = os.path.getsize(file)
        if size >= 1000000:
            print("    Large file: "+file+" ("+str(round(size/1000000,1))+" MB)")
        if filetype=="vmt":
            file = open(file,'r')
            content = file.readlines()
            file.close()
            for line in content:
                parts = shlex.split(line.lower())
                if len(parts)>=2 and (parts[0].replace("2","") in vtf_keys):
                    depends.append("materials/"+parts[1]+".vtf")
                
        elif filetype=="mdl":
            depends.append(filebase+".dx80.vtx")
            depends.append(filebase+".dx90.vtx")
            depends.append(filebase+".phy")
            depends.append(filebase+".sw.vtx")
            depends.append(filebase+".vvd")
            file = open(file,'rb')
            file.seek(204)
            texture_count, = struct.unpack('<i', file.read(4))
            texture_offset, = struct.unpack('<i', file.read(4))
            texturedir_count, = struct.unpack('<i', file.read(4))
            texturedir_offset, = struct.unpack('<i', file.read(4))
            textureoffsets = []
            file.seek(texture_offset)
            while texture_count>0:
                next, = struct.unpack('<i', file.read(4))
                textureoffsets.append(file.tell()-4+next)
                file.seek(file.tell()+60)
                texture_count = texture_count - 1
            texturediroffsets = []
            file.seek(texturedir_offset)
            while texturedir_count>0:
                next, = struct.unpack('<i', file.read(4))
                texturediroffsets.append(next)
                texturedir_count = texturedir_count - 1
            textures=[]
            for offset in textureoffsets:
                file.seek(offset)
                textures.append(readcstr(file))
            texturedirs=[]
            #If for some reason there are multiple texturedirs, just look for all combinations
            for offset in texturediroffsets:
                file.seek(offset)
                tdir = readcstr(file)
                for tex in textures:
                    depends.append("materials/"+tdir+tex+".vmt")
            
    else:
        #It's not available, so don't try to pack it
        deletethis = True
                  
    return depends,deletethis

main()
