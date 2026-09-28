import subprocess, sys
S="/root/.claude/uploads/702fee8f-3cbe-5239-af99-f1b2098d7a56/"
A=S+"c1cd4e31-Adobe_Express_-_IMG_6284-2.mp4"; B=S+"fad40645-Adobe_Express_-_IMG_6289.mp4"
OUT=sys.argv[1]
PRE,POST=0.06,0.09
# speech islands (from silencedetect -40dB, pauses < 0.25s kept)
speechA=[(2.227,3.720),(4.100,5.136),(5.780,7.640),(7.969,11.027),(11.541,12.068)]
speechB=[(2.068,7.382),(7.803,10.657)]
G="eq=saturation=0.82:contrast=1.07:brightness=-0.012:gamma=0.98,lutyuv=u=val+0.3:v=val+2"
TOUT,TIN,ZMAX=0.20,0.28,1.45   # zoom-through transition
PUNCH=1.12
def zoomv(expr):
    return (f"scale=w='2*trunc(540*({expr}))':h='2*trunc(960*({expr}))':eval=frame,"
            f"crop=1080:1920:x='(iw-1080)*0.5':y='(ih-1920)*0.33',setsar=1")
FR=1001/30000
q=lambda x: round(x/FR)*FR
segs=[]  # (input_idx, start, end, zoom_expr, grade, blur)
for i,(s,e) in enumerate(speechA):
    a,b=q(s-PRE),q(e+POST)
    z=f"{PUNCH}" if i%2 else "1"
    if i==len(speechA)-1:
        segs.append((0,a,q(b-TOUT),z,False,False))
        # ease-in zoom to ZMAX over tail
        segs.append((0,q(b-TOUT),b,f"1+{ZMAX-1}*pow(t/{TOUT},2)",False,True))
    else: segs.append((0,a,b,z,False,False))
for i,(s,e) in enumerate(speechB):
    a,b=q(s-PRE),q(e+POST)
    if i==0:
        segs.append((1,a,q(a+TIN),f"1+{ZMAX-1}*pow(1-min(t/{TIN},1),2)",True,True))
        segs.append((1,q(a+TIN),b,"1",True,False))
    else: segs.append((1,a,b,f"{PUNCH}",True,False))
fc=[];vl=[];al=[]
T=[k for k,sg in enumerate(segs) if sg[5]]   # tail-of-A, head-of-B
for k,(inp,a,b,z,g,bl) in enumerate(segs):
    v=f"[{inp}:v]trim=start_frame={round(a/FR)}:end_frame={round(b/FR)},setpts=N/(30000/1001)/TB,"+(G+"," if g else "")+zoomv(z)
    fc.append(v+f",setpts=N/(30000/1001)/TB,format=yuv420p[v{k}]")
    fc.append(f"[{inp}:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,"+("volume=-1.7dB," if inp else "")+
              f"afade=t=in:d=0.012,afade=t=out:st={b-a-0.015:.3f}:d=0.015[a{k}]")
    al.append(f"[a{k}]")
tl=segs[T[0]][2]-segs[T[0]][1]
fc.append(f"[v{T[0]}][v{T[1]}]concat=n=2:v=1:a=0,tmix=frames=5:weights='1 1 1 1 1',"
          f"gblur=sigma=3,gblur=sigma=10:enable='between(t,{tl-0.07:.3f},{tl+0.07:.3f})',"
          f"eq=brightness=0.06:enable='between(t,{tl-0.035:.3f},{tl+0.035:.3f})',setpts=N/(30000/1001)/TB[vt]")
for k in range(len(segs)):
    if k==T[0]: vl.append("[vt]")
    elif k not in T: vl.append(f"[v{k}]")
fc.append("".join(vl)+f"concat=n={len(vl)}:v=1:a=0[vc];[vc]settb=1001/30000,setpts=N,fps=30000/1001[v]")
fc.append("".join(al)+f"concat=n={len(al)}:v=0:a=1[sp]")
# whoosh centred on the cut
tcut=sum(b-a for (i,a,b,*_) in segs if i==0)
fc.append(f"anoisesrc=color=pink:d=0.5:a=0.5:r=48000,highpass=f=300,lowpass=f=4000,"
          f"afade=t=in:d=0.3:curve=exp,afade=t=out:st=0.3:d=0.2,volume=-14dB,aformat=channel_layouts=stereo,"
          f"adelay={int((tcut-0.3)*1000)}|{int((tcut-0.3)*1000)}[wh]")
fc.append("[sp]highpass=f=80,acompressor=threshold=-24dB:ratio=2.5:attack=10:release=150:makeup=2[spc]")
fc.append("[spc][wh]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=7[a]")
cmd=["ffmpeg","-v","error","-y","-i",A,"-i",B,"-filter_complex",";".join(fc),"-map","[v]","-map","[a]",
     "-ar","48000","-r","30000/1001","-c:v","libx264","-preset","slow","-crf","16","-pix_fmt","yuv420p","-c:a","aac","-b:a","256k",
     "-movflags","+faststart",OUT]
print("cut at",round(tcut,3),"total",round(sum(b-a for _,a,b,*r in segs),3))
subprocess.run(cmd,check=True)
