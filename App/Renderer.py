import os, math
import platform as platformModule
import time as timeModule

import pygame
from pygame.locals import *
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *

from Common import logger, log_level, COMMAND
from Utilities import *
from Object import Camera, Light
from OpenGLContext import RenderTargets, RenderTargetManager, FrameBuffer, GLFont, UniformMatrix4, UniformBlock


class Console:
    def __init__(self):
        self.infos = []
        self.debugs = []
        self.renderer = None
        self.texture = None
        self.font = None
        self.enable = True

    def initialize(self, renderer):
        self.renderer = renderer
        self.font = GLFont(self.renderer.coreManager.resource_manager.DefaultFontFile, 12, margin=(10, 0))

    def close(self):
        pass

    def clear(self):
        self.infos = []

    def toggle(self):
        self.enable = not self.enable

    # just print info
    def info(self, text):
        if self.enable:
            self.infos.append(text)

    # debug text - print every frame
    def debug(self, text):
        if self.enable:
            self.debugs.append(text)

    def render(self):
        self.renderer.ortho_view()

        # set render state
        glEnable(GL_BLEND)
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glDisable(GL_LIGHTING)

        if self.enable and self.infos:
            text = '\n'.join(self.infos) if len(self.infos) > 1 else self.infos[0]
            if text:
                # render
                self.font.render(text, 0, self.renderer.height - self.font.height)
            self.infos = []


class Renderer(Singleton):
    def __init__(self):
        self.width = 1024
        self.height = 768
        self.viewportRatio = float(self.width) / float(self.height)
        self.viewMode = GL_FILL
        # managers
        self.coreManager = None
        self.resource_manager = None
        self.sceneManager = None
        self.rendertarget_manager = None
        # console font
        self.console = None
        # components
        self.lastShader = None
        self.screen = None
        self.framebuffer = None
        self.framebuffer_shadowmap = None

        # Test Code : scene constants uniform buffer
        self.uniformSceneConstants = None
        self.uniformLightConstants = None

    @staticmethod
    def destroyScreen():
        # destroy
        pygame.display.quit()

    def initialize(self, core_manager, width, height, screen):
        logger.info("Initialize Renderer")
        self.width = width
        self.height = height
        self.screen = screen

        self.coreManager = core_manager
        self.resource_manager = core_manager.resource_manager
        self.sceneManager = core_manager.sceneManager
        self.rendertarget_manager = RenderTargetManager.instance()
        self.framebuffer = FrameBuffer()
        self.framebuffer_shadowmap = FrameBuffer()

        # console font
        self.console = Console()
        self.console.initialize(self)

        # Test Code : scene constants uniform buffer
        material_instance = self.resource_manager.getMaterialInstance('scene_constants')
        program = material_instance.get_program()
        self.uniformSceneConstants = UniformBlock("sceneConstants", program, 0,
                                                  [MATRIX4_IDENTITY,
                                                   MATRIX4_IDENTITY,
                                                   FLOAT4_ZERO])
        self.uniformLightConstants = UniformBlock("lightConstants", program, 1,
                                                  [FLOAT4_ZERO,
                                                   FLOAT4_ZERO,
                                                   FLOAT4_ZERO])

        # set gl hint
        glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)

    def close(self):
        # destroy console
        if self.console:
            self.console.close()

    def setViewMode(self, viewMode):
        if viewMode == COMMAND.VIEWMODE_WIREFRAME:
            self.viewMode = GL_LINE
        elif viewMode == COMMAND.VIEWMODE_SHADING:
            self.viewMode = GL_FILL

    def resizeScene(self, width=0, height=0):
        # You have to do pygame.display.set_mode again on Linux.
        if width <= 0 or height <= 0:
            width = self.width
            height = self.height
            if width <= 0:
                width = 1024
            if height <= 0:
                height = 768

        self.width = width
        self.height = height
        self.viewportRatio = float(width) / float(height)

        camera = self.sceneManager.getMainCamera()

        # update perspective and ortho
        camera.update_viewport(width, height, self.viewportRatio)

        # resize render targets
        self.rendertarget_manager.create_rendertargets(self.width, self.height)

        # Run pygame.display.set_mode at last!!! very important.
        if platformModule.system() == 'Linux':
            self.screen = pygame.display.set_mode((self.width, self.height),
                                                  OPENGL | DOUBLEBUF | RESIZABLE | HWPALETTE | HWSURFACE)

    def ortho_view(self):
        # Legacy opengl pipeline - set orthographic view
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def projection_view(self):
        # Legacy opengl pipeline - set perspective view
        camera = self.sceneManager.getMainCamera()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(camera.fov, self.viewportRatio, camera.near, camera.far)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def renderScene(self):
        startTime = timeModule.perf_counter()

        # bind scene constants
        camera = self.sceneManager.getMainCamera()
        lights = self.sceneManager.get_object_list(Light)
        vp_matrix = None

        if not camera or len(lights) < 1:
            return

        colortexture_copy = self.rendertarget_manager.get_rendertarget(RenderTargets.BACKBUFFER_COPY)
        shadowmap = self.rendertarget_manager.get_rendertarget(RenderTargets.SHADOWMAP)
        self.framebuffer_shadowmap.set_color_texture(colortexture_copy, (0.0, 0.0, 0.0, 1.0))
        self.framebuffer_shadowmap.set_depth_texture(shadowmap, (1.0, 1.0, 1.0, 0.0))
        self.framebuffer_shadowmap.bind_framebuffer()

        self.uniformSceneConstants.bindData(camera.get_view_matrix(),
                                            camera.perspective,
                                            camera.transform.getPos(),
                                            FLOAT_ZERO)

        light = lights[0]
        light.transform.setPos((math.sin(timeModule.time()) * 20.0, 0.0, math.cos(timeModule.time()) * 20.0))
        light.transform.updateInverseTransform()  # update view matrix
        self.uniformLightConstants.bindData(light.transform.getPos(), FLOAT_ZERO,
                                            light.transform.front, FLOAT_ZERO,
                                            light.lightColor)

        # render shadow
        vp_matrix = np.dot(light.transform.inverse_matrix, camera.perspective)
        self.render_objects(vp_matrix)
        self.framebuffer_shadowmap.unbind_framebuffer()

        # render object
        colortexture = self.rendertarget_manager.get_rendertarget(RenderTargets.BACKBUFFER)
        depthtexture = self.rendertarget_manager.get_rendertarget(RenderTargets.DEPTHSTENCIL)

        self.framebuffer.set_color_texture(colortexture, (0.0, 0.0, 0.0, 1.0))
        self.framebuffer.set_depth_texture(depthtexture, (1.0, 1.0, 1.0, 0.0))

        # bind back buffer and depth buffer, then clear
        self.framebuffer.bind_framebuffer()

        default_material_instance = self.resource_manager.getDefaultMaterialInstance()
        default_material_instance.useProgram()
        shadowmap = self.rendertarget_manager.get_rendertarget(RenderTargets.BACKBUFFER_COPY)
        default_material_instance.bind_uniform_data("texture_shadow", shadowmap)
        default_material_instance.bind()
        vp_matrix = camera.vp_matrix
        self.render_objects(vp_matrix)

        # self.render_bones()
        # self.render_postprocess()

        # reset shader program
        glUseProgram(0)

        # render text
        self.console.render()

        # blit frame buffer
        self.framebuffer.blitFramebuffer(self.width, self.height)

        endTime = timeModule.perf_counter()
        renderTime = endTime - startTime
        startTime = endTime

        # swap buffer
        pygame.display.flip()
        presentTime = timeModule.perf_counter() - startTime
        return renderTime, presentTime

    def render_objects(self, vpMatrix, specify_material_instance=None):
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_CULL_FACE)
        glFrontFace(GL_CCW)
        glDisable(GL_BLEND)
        glEnable(GL_LIGHTING)
        glShadeModel(GL_SMOOTH)
        glPolygonMode(GL_FRONT_AND_BACK, self.viewMode)

        # Test Code : sort list by mesh, material
        static_actors = self.sceneManager.get_static_actors()[:]
        geometries = []
        for static_actor in static_actors:
            geometries += static_actor.geometries
        geometries.sort(key=lambda x: id(x.vertex_buffer))

        # draw static meshes
        default_material_instance = self.resource_manager.getDefaultMaterialInstance()
        last_vertex_buffer = None
        last_material = None
        last_material_instance = None
        last_actor = None
        for geometry in geometries:
            actor = geometry.parent_actor
            if specify_material_instance:
                material_instance = specify_material_instance
            else:
                material_instance = geometry.material_instance or default_material_instance
            material = material_instance.material if material_instance else None

            if last_material != material and material is not None:
                material.useProgram()

            if last_material_instance != material_instance and material_instance is not None:
                material_instance.bind()

            # At last, bind buffers
            if geometry is not None and last_vertex_buffer != geometry.vertex_buffer:
                geometry.bindBuffer()

            if last_actor != actor and material_instance:
                material_instance.bind_uniform_data('model', actor.transform.matrix)
                material_instance.bind_uniform_data('mvp', np.dot(actor.transform.matrix, vpMatrix))
                if 0 < actor.mesh.get_animation_frame_count():
                    animation_buffer = actor.get_animation_buffer()
                    material_instance.bind_uniform_data('bone_matrices', animation_buffer, len(animation_buffer))

            # draw
            if geometry and material_instance:
                geometry.draw()

            last_actor = actor
            last_material = material
            last_vertex_buffer = geometry.vertex_buffer
            last_material_instance = material_instance

    def render_bones(self):
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        mesh = self.resource_manager.getMesh("Cube")
        material_instance = self.resource_manager.getMaterialInstance("debug_bone")
        static_actors = self.sceneManager.get_static_actors()[:]

        if mesh and material_instance:
            material_instance.useProgram()
            material_instance.bind()
            mesh.bindBuffer()

            def draw_bone(mesh, skeleton_mesh, parent_matrix, material_instance, bone, root_matrix, isAnimation):
                if isAnimation:
                    bone_transform = skeleton_mesh.get_animation_transform(bone.name, frame)
                else:
                    bone_transform = np.linalg.inv(bone.inv_bind_matrix)

                if bone.children:
                    for child_bone in bone.children:
                        if isAnimation:
                            bone_transform = skeleton_mesh.get_animation_transform(bone.name, frame)
                            child_transform = skeleton_mesh.get_animation_transform(child_bone.name, frame)
                        else:
                            bone_transform = np.linalg.inv(bone.inv_bind_matrix)
                            child_transform = np.linalg.inv(child_bone.inv_bind_matrix)
                        material_instance.bind_uniform_data("mat1", np.dot(bone_transform, root_matrix))
                        material_instance.bind_uniform_data("mat2", np.dot(child_transform, root_matrix))
                        mesh.draw()
                        draw_bone(mesh, skeleton_mesh, bone_transform.copy(), material_instance, child_bone, root_matrix, isAnimation)
                else:
                    material_instance.bind_uniform_data("mat1", np.dot(bone_transform, root_matrix))
                    child_transform = np.dot(bone_transform, root_matrix)
                    child_transform[3, :] += child_transform[1, :]
                    material_instance.bind_uniform_data("mat2", child_transform)
                    mesh.draw()

            for static_actor in static_actors:
                if static_actor.model and static_actor.model.mesh and static_actor.model.mesh.skeletons:
                    skeletons = static_actor.model.mesh.skeletons
                    skeleton_mesh = static_actor.model.mesh
                    frame_count = skeleton_mesh.get_animation_frame_count()
                    frame = math.fmod(self.coreManager.currentTime * 30.0, frame_count) if frame_count > 0.0 else 0.0
                    isAnimation = frame_count > 0.0
                    for skeleton in skeletons:
                        matrix = static_actor.transform.matrix
                        for bone in skeleton.hierachy:
                            draw_bone(mesh, skeleton_mesh, Matrix4().copy(), material_instance, bone, matrix, isAnimation)

    def render_postprocess(self):
        glEnable(GL_BLEND)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glDisable(GL_LIGHTING)
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        mesh = self.resource_manager.getMesh("Quad")
        mesh.bindBuffer()
        self.sceneManager.tonemapping.bind()
        mesh.draw()
