from App import CoreManager
from .RenderTarget import RenderTargets


class Fog:
    def __init__(self, **sky_datas):
        self.quad = None
        self.quad_geometry = None
        self.material_instance = None
        self.rendertarget_manager = None
        self.initialize()

    def initialize(self):
        core_manager = CoreManager.instance()
        resource_manager = core_manager.resource_manager
        self.rendertarget_manager = core_manager.rendertarget_manager

        self.quad = resource_manager.getMesh("Quad")
        self.quad_geometry = self.quad.get_geometry()
        self.material_instance = resource_manager.getMaterialInstance("fog")

    def render(self):
        self.quad_geometry.bind_vertex_buffer()
        self.material_instance.use_program()
        self.material_instance.bind_uniform_data('texture_linear_depth', RenderTargets.LINEAR_DEPTH)
        self.quad_geometry.draw_elements()
