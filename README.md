![PyEngine3D](https://github.com/ubuntunux/PyEngine3D/blob/master/PyEngine3D.png)

## What is PyEngine3D
* An open source OpenGL 3D engine written in Python.
* Homepage : https://pyengine3d.blogspot.com
* Documents : https://pyengine3d.readthedocs.io

### Requirements
 - numpy
 - pillow
 - pyglet or pygame
 - PyOpenGL
 - PyOpenGL-accelerate ( optional )
 - Windows, Linux, Mac(not tested)
 
## How to install PyEngine3D
```
  git clone https://github.com/ubuntunux/PyEngine3D
  cd PyEngine3D
  pip install -r requirements.txt
  python main.py
```
* Video : https://www.youtube.com/watch?v=bVwdV695_zo

## Features
* Import
    - Mesh 
        - [x] .fbx, .obj, .dae ( colada ) 
        - [ ] gltf, blender
    - Texture
        - [x] .png, .tga, .bmp etc 
        - [ ] Compressed Texture (ETC, DDS)
* Light
    - [x] Directional light & Shadow mapping    
    - [ ] Spot light
    - [ ] Area light
    - [x] Point light
        - [ ] shadow map using dual paraboloid mapping
* Particle System
    - [x] CPU Based Particle
    - [x] GPU Based Particle
    - [x] Vector Field
    - [ ] Particle spawn on polygon surface
    - [ ] Bitonic Sorting
    - [ ] Memory Pool
    - [ ] Attractor
    - [ ] Noise
    - [ ] Curl Noise
* Object
    - [ ] Select, Move, Modify
    - [ ] Gizmo
    - [x] Skeleton Mesh
    - [x] Static Mesh        
    - [ ] Tree, Foliage, Grass
    - [x] Terrain
    - [x] Atmoshpere & Sky
    - [ ] Road
    - [ ] Wind
    - [x] FFT Ocean
    - [ ] River 
* Rendering
    - [ ] Culling
        - [ ] occlusion culling
        - [ ] distance culling
        - [x] view frustum culling
    - [ ] VTF Skinning
    - [ ] Calculate the animation in gpu
    - [ ] Distance Field Font 
    - [x] Real time light probe 
    - [x] PBR
    - [x] Temporal AA
    - [x] SSAA
    - [x] MSAA
    - [ ] Temporal Upsacle
    - [x] Screen Space Relfection
    ![Screen Space Relfection](https://github.com/ubuntunux/PyEngine3D/blob/master/PyEngine3D.png)
    - [x] Screen Space Ambient Occlusion
    - [ ] Screen Space Bevel
    - [ ] Screen Space SSS    
    - [x] Depth Of Field
        - [ ] Bokeh
    - [x] Bloom
    - [x] Tone mapping
    - [ ] Glare
    - [ ] Film Grain
    - [ ] Color Correction
    - [ ] Color Grading
    - [x] Light Shaft
    - [x] Motion Blur
        - [ ] Recursive Velocity
    - [ ] Parallax Occlusion Rendering
    - [ ] Paraboloid environment map    
    - [ ] Voxel Based GI
    - [ ] Volumtric Scattering
    - [ ] Fur Rendering    
* Resource Manager
    - [x] Load / Save / Import / Export
    - [ ] Unload / Reload system
    - [ ] Duplicate resource
    - [ ] Sound Manager
    - [x] Script Manager
* Blender3D plugin
    - [ ] transfer geometry, animation, scene datas
    - [ ] edit animation, scene, sequence, particles in blender
* InGame GUI
    - [ ] input / output
    - [ ] progress bar
    - [ ] button
* Optimize
    - [ ] Only dynamic shadows are updated on every frame, and static shadows are not updated every time.
    - [ ] SSR ray reuse in compute shader
    - [ ] Postprocessing in compute shader
    - [ ] FFT in compute shader
    - [ ] Precomputed atmosphere in compute shader 


## References
    - https://wickedengine.net/2017/11/07/gpu-based-particle-simulation/
    - http://kode80.com/blog/2015/03/11/screen-space-reflections-in-unity-5/index.html
    - http://proland.inrialpes.fr/publications.html
    - http://casual-effects.com/data/index.html
    - https://github.com/TheRealMJP/MSAAFilter
    - http://pyopengl.sourceforge.net/
    - https://learnopengl.com/
    - http://www.songho.ca/index.html
