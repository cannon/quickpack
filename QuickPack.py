import struct
import re
import os
import shlex
import sys
import functools
import itertools
import zipfile
import shutil

#vmt parameters that reference a vtf texture (all $...2 parameters work as well)
vtf_keys = set(['$basetexture','$detail','$blendmodulatetexture','$bumpmap','$normalmap','$parallaxmap','$heightmap','$selfillummask','$lightwarptexture','$envmap','$envmapmask','$displacementmap','$reflecttexture','$refracttexture','$refracttinttexture','$dudvmap'])
vmt_keys = set(['$bottommaterial','$underwateroverlay'])

#dictionary mdlfile->set(skins) so we don't pack unused skins
model_skins = {}

#set of models we'll use every single skin on
all_model_skins = set()

#main file list (filename->boolean have we checked it for subdependencies)
dependencies = {}

#exclusion list (from nopack.txt)
dontpack = set()

def main():
    print("\nQuickPack v1.4 by Jackson Cannon - https://github.com/cannon/quickpack")

    if len(sys.argv) < 2:
        print("Usage: "+sys.argv[0]+" path/to/filename.bsp")
        sys.exit()

    abspath = os.path.abspath(sys.argv[1])
    if not os.path.isfile(abspath):
        print("File does not exist: "+abspath)
        sys.exit()

    pathparts = sys.argv[1].replace("/","\\").split("\\")
    
    if not pathparts[-1].lower().endswith(".bsp"):
        print("Not a BSP file: "+abspath)
        sys.exit()

    if not pathparts[-2].lower() == "maps":
        print("Not in a valid game directory: "+abspath)
        sys.exit()

    os.chdir('\\'.join(pathparts[0:-2]))

    gameroot = os.getcwd()
    mapfilepath = '/'.join(pathparts[-2:]).lower()
    mapfilepath_cmd = cmd_path(gameroot+"/"+mapfilepath)
    mapname = pathparts[-1].lower().replace(".bsp","")

    #Add global dependencies to look for
    dependencies["maps/"+mapname+".txt"] = False
    dependencies["maps/"+mapname+".nav"] = False
    dependencies["maps/"+mapname+".kv"] = False
    dependencies["maps/cfg/"+mapname+".cfg"] = False
    dependencies["resource/overviews/"+mapname+".txt"] = False
    dependencies["resource/overviews/"+mapname+"_radar.dds"] = False
    dependencies["resource/overviews/"+mapname+"_radar_spectate.dds"] = False
    dependencies["resource/overviews/"+mapname+"_lower_radar.dds"] = False
    dependencies["resource/overviews/"+mapname+"_higher_radar.dds"] = False

    textfile_name = mapfilepath.replace(".bsp",".pack.txt")
    if os.path.isfile(textfile_name):
        print("\nAdding files from "+(sanitize_filename(textfile_name).split("/")[-1])+"...")
        textfile = open(textfile_name,'r')
        textfilecontent = textfile.readlines()
        textfile.close()
        for i in textfilecontent:
            dependencies[sanitize_filename(i)] = False

    textfile_name = mapfilepath.replace(".bsp",".nopack.txt")
    if os.path.isfile(textfile_name):
        print("\nRemoving files from "+(sanitize_filename(textfile_name).split("/")[-1])+"...")
        textfile = open(textfile_name,'r')
        textfilecontent = textfile.readlines()
        textfile.close()
        for i in textfilecontent:
            dontpack.add(sanitize_filename(i))


    print("\nReading "+mapname+".bsp...")
  
    delete_file("maps/quickpacktemp.zip")
    delete_dir("maps/quickpacktemp")

    os.chdir("../bin")
    os.system("bspzip.exe -extract "+mapfilepath_cmd+" "+cmd_path(gameroot+"/maps/quickpacktemp.zip")+" > nul 2>&1")
    os.chdir(gameroot)

    #Unpack patch materials made by the compiler
    unpack_files = set()
    zf = zipfile.ZipFile("maps/quickpacktemp.zip")
    for f in zf.infolist():
        f = sanitize_filename(f.filename)
        if f.startswith("materials/maps/"):
            unpack_files.add(f)
    zf.extractall("maps/quickpacktemp",unpack_files)
    zf.close()
    delete_file("maps/quickpacktemp.zip")
    
    for f in unpack_files:
        dependencies[sanitize_filename("maps/quickpacktemp/"+f)]=False
    
    bsp_file = open(sys.argv[1],'rb')

    read_texture_lump(bsp_file)
    read_staticprop_lump(bsp_file)
    read_entity_lump(bsp_file) #this must come after read_staticprop_lump

    bsp_file.close()


    print("Finding dependencies...")

    moreitems = True
    while moreitems:
        moreitems = False
        for file, checked in list(dependencies.items()):
            if file in dontpack:
                del dependencies[file]
                continue
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

    for file, checked in list(dependencies.items()):
        if file.startswith("maps/quickpacktemp"):
            del dependencies[file]
    delete_dir("maps/quickpacktemp")

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

    delete_file("quickpack.txt")

    outfile = open("quickpack.txt","w")
    for file, checked in dependencies.items():
        outfile.write(file+'\n')
        outfile.write(gameroot+"\\"+(file.replace("/","\\"))+'\n')

    outfile.close()

    os.system("bspzip.exe -addlist "+mapfilepath_cmd+" quickpack.txt "+mapfilepath_cmd+" > nul 2>&1")

    delete_file("quickpack.txt")

    print("Done!")

def debug_bytes(bytes):
    import binascii
    bytes = binascii.hexlify(bytes)
    split = 2*12
    print(' '.join(bytes[i:i+split] for i in xrange(0,len(bytes),split)))
    return

def regex_find(regex, data):
    regex = re.compile(regex,re.IGNORECASE)
    data = re.findall(regex, data)
    data = set(list(map(lambda x: sanitize_filename(x.decode("ascii")), data)))
    return data

def readcstr(f):
    toeof = iter(functools.partial(f.read, 1), '')
    return ''.join(itertools.takewhile('\0'.__ne__, toeof))

def cmd_path(p):
    if (' ' in p) and (not ('"' in p)):
        p = '"'+p+'"'
    return p.replace("/","\\")

def delete_file(f):
    if os.path.isfile(f):
        os.remove(f)

def delete_dir(f):
    if os.path.isdir(f):
        shutil.rmtree(f)

def vtf_filename(file):
    return "materials/"+sanitize_filename(file)+".vtf"

def vmt_filename(file):
    file = "materials/"+sanitize_filename(file)
    if not file.endswith(".vmt"):
        file = file+".vmt"
    return file

def sanitize_filename(file):
    return file.lower().replace("\\","/").strip().strip("/")

def check_file(filename):
    filebase = filename.split(".",1)[0]
    filetype = filename.split(".",1)[-1]
    depends = []
    deletethis = False

    #if file doesn't exist, we assume it's in a vpk so no need to pack
    if os.path.isfile(filename):
        size = os.path.getsize(filename)
        if size >= 1000000:
            print("    Large file: "+filename+" ("+str(round(size/1000000.0,1))+" MB)")
        if filetype=="vmt":
            file = open(filename,'r')
            content = shlex.split(file.read().lower())
            while len(content) >= 2:
                key = content.pop(0)
                if key.replace("2","") in vtf_keys:
                    depends.append(vtf_filename(content.pop(0)))
                elif key in vmt_keys:
                    depends.append(vmt_filename(content.pop(0)))
                elif key=="include":
                    depends.append(content.pop(0))
            file.close()
                
        elif filetype=="mdl":
            depends.append(filebase+".dx80.vtx")
            depends.append(filebase+".dx90.vtx")
            depends.append(filebase+".phy")
            depends.append(filebase+".sw.vtx")
            depends.append(filebase+".vvd")
            file = open(filename,'rb')
            file.seek(204)
            texture_count, = struct.unpack('<i', file.read(4))
            texture_offset, = struct.unpack('<i', file.read(4))
            texturedir_count, = struct.unpack('<i', file.read(4))
            texturedir_offset, = struct.unpack('<i', file.read(4))
            skinreference_count, = struct.unpack('<i', file.read(4))
            skinrfamily_count, = struct.unpack('<i', file.read(4))
            skinreference_index, = struct.unpack('<i', file.read(4))

            used_materials = set()

            if filename in all_model_skins:
                used_materials=set([x for x in range(skinreference_count)])
            else:
                file.seek(skinreference_index)
                this_skinreference = 0
                this_skinfamily = 0
                skins_to_read = skinreference_count*skinrfamily_count

                skintable = [[0 for y in range(skinrfamily_count)] for x in range(skinreference_count)] 
                while skins_to_read > 0:
                    next, = struct.unpack('<H', file.read(2))
                    skintable[this_skinreference][this_skinfamily] = next
                    this_skinreference = this_skinreference+1
                    if this_skinreference>=skinreference_count:
                        this_skinreference=0
                        this_skinfamily=this_skinfamily+1
                    skins_to_read = skins_to_read-1

                #Thanks to ZeqMacaw for helping figure this part out (filtering skin table columns)
                last_different_column = 0
                last_newindex_column = 0
                unseen_indexes = set([x for x in range(skinreference_count)])
                for x in range(skinreference_count):
                    for y in range(skinrfamily_count):
                        if skintable[x][0]!=skintable[x][y]:
                            last_different_column=x
                        if skintable[x][y] in unseen_indexes:
                            last_newindex_column=x
                            unseen_indexes.remove(skintable[x][y])

                
                last_column = max(last_different_column,last_newindex_column)

                skin_to_textures = {}
                for skin in range(skinrfamily_count):
                    skin_to_textures[skin] = set()
                    for x in range(last_column+1):
                        skin_to_textures[skin].add(skintable[x][skin])

                for skin in model_skins[filename]:
                    if skin in skin_to_textures:
                        for i in skin_to_textures[skin]:
                            used_materials.add(i)

            textureoffsets = []
            file.seek(texture_offset)
            tex_id = 0
            while texture_count>0:                                                                               
                next, = struct.unpack('<i', file.read(4))
                name_spot = file.tell()-4+next
                file.seek(file.tell()+60)
                texture_count = texture_count - 1
                if tex_id in used_materials:
                    textureoffsets.append(name_spot)
                tex_id = tex_id + 1
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
                    depends.append(vmt_filename(tdir+tex))

            file.close()
            
    else:
        #It's not available, so don't try to pack it
        deletethis = True
                  
    return depends,deletethis

def read_texture_lump(bsp_file):
    texturelump = read_lump(bsp_file, 43)

    #Find (brush) Materials
    maptextures = texturelump.split(b'\0')[:-1]

    for i in maptextures:
        dependencies[vmt_filename(i.decode("ascii"))] = False

#Add staticprop mdl files into dependencies and add used skins to model_skins
def read_staticprop_lump(bsp_file):
    bsp_file.seek(8 + (35*16))
    fileofs, = struct.unpack('<i', bsp_file.read(4))
    filelen, = struct.unpack('<i', bsp_file.read(4))
    bsp_file.seek(fileofs)
    lumpcount, = struct.unpack('<i', bsp_file.read(4))
    while lumpcount>0:
        lumpcount = lumpcount - 1
        lumpid, = struct.unpack('<i', bsp_file.read(4))
        bsp_file.seek(bsp_file.tell()+2)
        lumpversion, = struct.unpack('<H', bsp_file.read(2))
        fileofs, = struct.unpack('<i', bsp_file.read(4))
        filelen, = struct.unpack('<i', bsp_file.read(4))
        last_pos = bsp_file.tell()
        #static prop lump
        if lumpid == 1936749168:
            bsp_file.seek(fileofs)
            dict_items, = struct.unpack('<i', bsp_file.read(4))
            bsp_file.seek(128*dict_items, 1)
            leafEntries, = struct.unpack('<i', bsp_file.read(4))
            bsp_file.seek(2*leafEntries, 1)
            static_props, = struct.unpack('<i', bsp_file.read(4))
            staticpropstart = bsp_file.tell()
            while static_props > 0:
                static_props = static_props - 1 
                bsp_file.seek(24, 1)
                modelid, = struct.unpack('<H', bsp_file.read(2))
                bsp_file.seek(6, 1)
                skin, = struct.unpack('<i', bsp_file.read(4))
                bsp_file.seek(20, 1)
                if lumpversion >= 5:
                    bsp_file.seek(4, 1)
                if lumpversion==6 or lumpversion==7 or lumpversion==8:
                    bsp_file.seek(4, 1)
                if lumpversion >= 7:
                    bsp_file.seek(4, 1)
                if lumpversion >= 10:
                    bsp_file.seek(4, 1)
                # Might be incorrect. It's a bool, but I think it's aligned to take up 4 bytes.
                if lumpversion >= 9:
                    bsp_file.seek(4, 1)
                
                staticpropstart = bsp_file.tell()
                bsp_file.seek(fileofs + 4 + (modelid*128))
                prop = readcstr(bsp_file)
                add_mdl_file(prop, skin)
                bsp_file.seek(staticpropstart)
        bsp_file.seek(last_pos)

def read_entity_lump(bsp_file):
    entitylump = read_lump(bsp_file, 0).decode("utf-8")
    entity_list = []
    this_entity = {}
    for line in entitylump.split('\n')[:-1]:
        line = line.strip()
        if line=="{":
            pass
        elif line=="}":
            entity_list.append(this_entity)
            this_entity = {}
        else:
            parts = shlex.split(line.lower())
            this_entity[parts[0]] = parts[1]

    for ent in entity_list:
        for k,v in ent.items():
            k=k.lower()
            if k=='model' and v[0]!='*':
                skin = -1
                #only pack this model's skin, UNLESS it has a targetname, in which case it might change
                for k2,v2 in ent.items():
                    if k2=='skin':
                        skin=int(v2)
                for k2,v2 in ent.items():
                    if k2=='targetname':
                        skin=-1
                add_mdl_file(v,skin)

            #env_sprite uses "model" as the key for its material
            if k=='texture' or k=='material' or k=='detailmaterial' or k=='model':
                dependencies[vmt_filename(v)] = False

            if k=='skyname':
                dependencies[vmt_filename("skybox/"+v+"bk")] = False
                dependencies[vmt_filename("skybox/"+v+"dn")] = False
                dependencies[vmt_filename("skybox/"+v+"ft")] = False
                dependencies[vmt_filename("skybox/"+v+"lf")] = False
                dependencies[vmt_filename("skybox/"+v+"rt")] = False
                dependencies[vmt_filename("skybox/"+v+"up")] = False

    #Find Sounds
    #todo: implement into above part (there are numerous entity keys that can reference a sound)
    mapsounds = regex_find(b"[a-z0-9_\\- /\\\\]+\\.wav", entitylump)
    mapsounds = mapsounds.union(regex_find(b"[a-z0-9_\\- /\\\\]+\\.ogg", entitylump))
    mapsounds = mapsounds.union(regex_find(b"[a-z0-9_\\- /\\\\]+\\.mp3", entitylump))

    for i in mapsounds:
        dependencies["sound/"+i] = False

#read a whole lump into a bytestring
def read_lump(bsp_file, id):
    bsp_file.seek(8 + (id*16))
    fileofs, = struct.unpack('<i', bsp_file.read(4))
    filelen, = struct.unpack('<i', bsp_file.read(4))
    bsp_file.seek(fileofs)
    return bsp_file.read(filelen)

#add skin of prop (-1 for all skins)
def add_mdl_file(prop,skin):
    dependencies[sanitize_filename(prop)] = False
    if skin==-1:
        all_model_skins.add(prop)
    else:
        if prop in model_skins:
            model_skins[prop].add(skin)
        else:
            model_skins[prop]=set([skin])
main()
