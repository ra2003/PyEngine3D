from math import cos, sin
import numpy as np

from OpenGL.GL import *

from .constants import *

from Utilities import *
from App import CoreManager
from OpenGLContext import CreateTexture, Texture2D, Texture3D, VertexArrayBuffer


def CieColorMatchingFunctionTableValue(wavelength, column):
    if wavelength <= kLambdaMin or wavelength >= kLambdaMax:
        return 0.0

    u = (wavelength - kLambdaMin) / 5.0
    row = int(u)
    assert(row >= 0 and row + 1 < 95)
    assert(CIE_2_DEG_COLOR_MATCHING_FUNCTIONS[4 * row] <= wavelength and
           CIE_2_DEG_COLOR_MATCHING_FUNCTIONS[4 * (row + 1)] >= wavelength)

    u -= row
    return CIE_2_DEG_COLOR_MATCHING_FUNCTIONS[4 * row + column] * (1.0 - u) + \
        CIE_2_DEG_COLOR_MATCHING_FUNCTIONS[4 * (row + 1) + column] * u


def Interpolate(wavelengths, wavelength_function, wavelength):
    assert(len(wavelength_function) == len(wavelengths))
    if wavelength < wavelengths[0]:
        return wavelength_function[0]

    for i in range(len(wavelengths) - 1):
        if wavelength < wavelengths[i + 1]:
            u = (wavelength - wavelengths[i]) / (wavelengths[i + 1] - wavelengths[i])
            return wavelength_function[i] * (1.0 - u) + wavelength_function[i + 1] * u
    return wavelength_function[wavelength_function.size() - 1]


# The returned constants are in lumen.nm / watt.
def ComputeSpectralRadianceToLuminanceFactors(wavelengths, solar_irradiance, lambda_power):
    k_r = 0.0
    k_g = 0.0
    k_b = 0.0

    solar_r = Interpolate(wavelengths, solar_irradiance, kLambdaR)
    solar_g = Interpolate(wavelengths, solar_irradiance, kLambdaG)
    solar_b = Interpolate(wavelengths, solar_irradiance, kLambdaB)
    dlambda = 1

    for L in range(kLambdaMin, kLambdaMax, dlambda):
        x_bar = CieColorMatchingFunctionTableValue(L, 1)
        y_bar = CieColorMatchingFunctionTableValue(L, 2)
        z_bar = CieColorMatchingFunctionTableValue(L, 3)
        r_bar = XYZ_TO_SRGB[0] * x_bar + XYZ_TO_SRGB[1] * y_bar + XYZ_TO_SRGB[2] * z_bar
        g_bar = XYZ_TO_SRGB[3] * x_bar + XYZ_TO_SRGB[4] * y_bar + XYZ_TO_SRGB[5] * z_bar
        b_bar = XYZ_TO_SRGB[6] * x_bar + XYZ_TO_SRGB[7] * y_bar + XYZ_TO_SRGB[8] * z_bar
        irradiance = Interpolate(wavelengths, solar_irradiance, L)
        k_r += r_bar * irradiance / solar_r * pow(L / kLambdaR, lambda_power)
        k_g += g_bar * irradiance / solar_g * pow(L / kLambdaG, lambda_power)
        k_b += b_bar * irradiance / solar_b * pow(L / kLambdaB, lambda_power)
    k_r *= MAX_LUMINOUS_EFFICACY * dlambda
    k_g *= MAX_LUMINOUS_EFFICACY * dlambda
    k_b *= MAX_LUMINOUS_EFFICACY * dlambda
    return [k_r, k_g, k_b]


def ConvertSpectrumToLinearSrgb(wavelengths, spectrum):
    x = 0.0
    y = 0.0
    z = 0.0
    dlambda = 1
    for L in range(kLambdaMin, kLambdaMax, dlambda):
        value = Interpolate(wavelengths, spectrum, L)
        x += CieColorMatchingFunctionTableValue(L, 1) * value
        y += CieColorMatchingFunctionTableValue(L, 2) * value
        z += CieColorMatchingFunctionTableValue(L, 3) * value

    r = MAX_LUMINOUS_EFFICACY * (XYZ_TO_SRGB[0] * x + XYZ_TO_SRGB[1] * y + XYZ_TO_SRGB[2] * z) * dlambda
    g = MAX_LUMINOUS_EFFICACY * (XYZ_TO_SRGB[3] * x + XYZ_TO_SRGB[4] * y + XYZ_TO_SRGB[5] * z) * dlambda
    b = MAX_LUMINOUS_EFFICACY * (XYZ_TO_SRGB[6] * x + XYZ_TO_SRGB[7] * y + XYZ_TO_SRGB[8] * z) * dlambda
    return r, g, b


class DensityProfileLayer:
    def __init__(self, width=0.0, exp_term=0.0, exp_scale=0.0, linear_term=0.0, constant_term=0.0):
        self.width = width
        self.exp_term = exp_term
        self.exp_scale = exp_scale
        self.linear_term = linear_term
        self.constant_term = constant_term


class Model:
    def __init__(self,
                 wavelengths,
                 solar_irradiance,
                 sun_angular_radius,
                 bottom_radius,
                 top_radius,
                 rayleigh_density,
                 rayleigh_scattering,
                 mie_density,
                 mie_scattering,
                 mie_extinction,
                 mie_phase_function_g,
                 absorption_density,
                 absorption_extinction,
                 ground_albedo,
                 max_sun_zenith_angle,
                 length_unit_in_meters,
                 use_luminance,
                 num_precomputed_wavelengths,
                 combine_scattering_textures):

        self.wavelengths = wavelengths
        self.solar_irradiance = solar_irradiance
        self.sun_angular_radius = sun_angular_radius
        self.bottom_radius = bottom_radius
        self.top_radius = top_radius
        self.rayleigh_density = rayleigh_density
        self.rayleigh_scattering = rayleigh_scattering
        self.mie_density = mie_density
        self.mie_scattering = mie_scattering
        self.mie_extinction = mie_extinction
        self.mie_phase_function_g = mie_phase_function_g
        self.absorption_density = absorption_density
        self.absorption_extinction = absorption_extinction
        self.ground_albedo = ground_albedo
        self.max_sun_zenith_angle = max_sun_zenith_angle
        self.length_unit_in_meters = length_unit_in_meters
        self.num_precomputed_wavelengths = num_precomputed_wavelengths
        self.combine_scattering_textures = combine_scattering_textures

        self.precompute_illuminance = num_precomputed_wavelengths > 3
        if self.precompute_illuminance:
            self.kSky = [MAX_LUMINOUS_EFFICACY, MAX_LUMINOUS_EFFICACY, MAX_LUMINOUS_EFFICACY]
        else:
            self.kSky = ComputeSpectralRadianceToLuminanceFactors(self.wavelengths, self.solar_irradiance, -3)
        self.kSun = ComputeSpectralRadianceToLuminanceFactors(self.wavelengths, self.solar_irradiance, 0)

        self.material_instance_macros = {
            'COMBINED_SCATTERING_TEXTURES': 1 if combine_scattering_textures else 0
        }

        # Atmosphere shader code
        resource_manager = CoreManager.instance().resource_manager
        shader_loader = resource_manager.shader_loader
        shader_name = 'precomputed_scattering.atmosphere_predefine'
        recompute_atmosphere_predefine = resource_manager.getShader(shader_name)
        recompute_atmosphere_predefine.shader_code = self.glsl_header_factory([kLambdaR, kLambdaG, kLambdaB])
        shader_loader.save_resource(shader_name)
        shader_loader.load_resource(shader_name)

        # create render targets
        rendertarget_manager = CoreManager.instance().rendertarget_manager

        self.transmittance_texture = rendertarget_manager.create_rendertarget(
            "transmittance_texture",
            Texture2D,
            width=TRANSMITTANCE_TEXTURE_WIDTH,
            height=TRANSMITTANCE_TEXTURE_HEIGHT,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP_TO_EDGE
        )

        self.scattering_texture = rendertarget_manager.create_rendertarget(
            "scattering_texture",
            Texture3D,
            width=SCATTERING_TEXTURE_WIDTH,
            height=SCATTERING_TEXTURE_HEIGHT,
            depth=SCATTERING_TEXTURE_DEPTH,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP_TO_EDGE
        )

        self.optional_single_mie_scattering_texture = None
        if not self.combine_scattering_textures:
            self.optional_single_mie_scattering_texture = rendertarget_manager.create_rendertarget(
                "optional_single_mie_scattering_texture",
                Texture3D,
                width=SCATTERING_TEXTURE_WIDTH,
                height=SCATTERING_TEXTURE_HEIGHT,
                depth=SCATTERING_TEXTURE_DEPTH,
                internal_format=GL_RGBA32F,
                texture_format=GL_RGBA,
                min_filter=GL_LINEAR,
                mag_filter=GL_LINEAR,
                data_type=GL_FLOAT,
                wrap=GL_CLAMP
            )

        self.irradiance_texture = rendertarget_manager.create_rendertarget(
            "irradiance_texture",
            Texture2D,
            width=IRRADIANCE_TEXTURE_WIDTH,
            height=IRRADIANCE_TEXTURE_HEIGHT,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP
        )

        self.delta_irradiance_texture = rendertarget_manager.create_rendertarget(
            "delta_irradiance_texture",
            Texture2D,
            width=IRRADIANCE_TEXTURE_WIDTH,
            height=IRRADIANCE_TEXTURE_HEIGHT,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP
        )

        self.delta_rayleigh_scattering_texture = rendertarget_manager.create_rendertarget(
            "delta_rayleigh_scattering_texture",
            Texture3D,
            width=SCATTERING_TEXTURE_WIDTH,
            height=SCATTERING_TEXTURE_HEIGHT,
            depth=SCATTERING_TEXTURE_DEPTH,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP
        )

        self.delta_mie_scattering_texture = rendertarget_manager.create_rendertarget(
            "delta_mie_scattering_texture",
            Texture3D,
            width=SCATTERING_TEXTURE_WIDTH,
            height=SCATTERING_TEXTURE_HEIGHT,
            depth=SCATTERING_TEXTURE_DEPTH,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP
        )

        self.delta_scattering_density_texture = rendertarget_manager.create_rendertarget(
            "delta_scattering_density_texture",
            Texture3D,
            width=SCATTERING_TEXTURE_WIDTH,
            height=SCATTERING_TEXTURE_HEIGHT,
            depth=SCATTERING_TEXTURE_DEPTH,
            internal_format=GL_RGBA32F,
            texture_format=GL_RGBA,
            min_filter=GL_LINEAR,
            mag_filter=GL_LINEAR,
            data_type=GL_FLOAT,
            wrap=GL_CLAMP
        )

        self.delta_multiple_scattering_texture = self.delta_rayleigh_scattering_texture

        positions = np.array([(-1, 1, 0, 1), (-1, -1, 0, 1), (1, -1, 0, 1), (1, 1, 0, 1)], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)

        self.quad = VertexArrayBuffer(
            name='precomputed atmosphere quad',
            datas=[positions, ],
            index_data=indices,
            dtype=np.float32
        )

    def glsl_header_factory(self, lambdas):
        def to_string(v, lambdas, scale):
            r = Interpolate(self.wavelengths, v, lambdas[0]) * scale
            g = Interpolate(self.wavelengths, v, lambdas[1]) * scale
            b = Interpolate(self.wavelengths, v, lambdas[2]) * scale
            return "vec3(%f, %f, %f)" % (r, g, b)

        def density_layer(layer):
            return "DensityProfileLayer(%f, %f, %f, %f, %f)" % (layer.width / self.length_unit_in_meters,
                                                                layer.exp_term,
                                                                layer.exp_scale * self.length_unit_in_meters,
                                                                layer.linear_term * self.length_unit_in_meters,
                                                                layer.constant_term)

        def density_profile(layers):
            kLayerCount = 2
            while len(layers) < kLayerCount:
                layers.insert(0, DensityProfileLayer())

            result = "DensityProfile(DensityProfileLayer[%d](" % kLayerCount
            for i in range(kLayerCount):
                result += density_layer(layers[i])
                if i < kLayerCount - 1:
                    result += ","
                else:
                    result += "))"
            return result

        sky_k_r, sky_k_g, sky_k_b = self.kSky[0], self.kSky[1], self.kSky[2]
        sun_k_r, sun_k_g, sun_k_b = self.kSun[0], self.kSun[1], self.kSun[2]

        resource_manager = CoreManager.instance().resource_manager
        definitions_glsl = resource_manager.getShader('precomputed_scattering.definitions').shader_code
        functions_glsl = resource_manager.getShader('precomputed_scattering.functions').shader_code

        header = ["const int TRANSMITTANCE_TEXTURE_WIDTH = %d;" % TRANSMITTANCE_TEXTURE_WIDTH,
                  "const int TRANSMITTANCE_TEXTURE_HEIGHT = %d;" % TRANSMITTANCE_TEXTURE_HEIGHT,
                  "const int SCATTERING_TEXTURE_R_SIZE = %d;" % SCATTERING_TEXTURE_R_SIZE,
                  "const int SCATTERING_TEXTURE_MU_SIZE = %d;" % SCATTERING_TEXTURE_MU_SIZE,
                  "const int SCATTERING_TEXTURE_MU_S_SIZE = %d;" % SCATTERING_TEXTURE_MU_S_SIZE,
                  "const int SCATTERING_TEXTURE_NU_SIZE = %d;" % SCATTERING_TEXTURE_NU_SIZE,
                  "const int IRRADIANCE_TEXTURE_WIDTH = %d;" % IRRADIANCE_TEXTURE_WIDTH,
                  "const int IRRADIANCE_TEXTURE_HEIGHT = %d;" % IRRADIANCE_TEXTURE_HEIGHT,
                  definitions_glsl,
                  "const AtmosphereParameters ATMOSPHERE = AtmosphereParameters(",
                  to_string(self.solar_irradiance, lambdas, 1.0) + ",",
                  str(self.sun_angular_radius) + ",",
                  str(self.bottom_radius / self.length_unit_in_meters) + ",",
                  str(self.top_radius / self.length_unit_in_meters) + ",",
                  density_profile(self.rayleigh_density) + ",",
                  to_string(self.rayleigh_scattering, lambdas, self.length_unit_in_meters) + ",",
                  density_profile(self.mie_density) + ",",
                  to_string(self.mie_scattering, lambdas, self.length_unit_in_meters) + ",",
                  to_string(self.mie_extinction, lambdas, self.length_unit_in_meters) + ",",
                  str(self.mie_phase_function_g) + ",",
                  density_profile(self.absorption_density) + ",",
                  to_string(self.absorption_extinction, lambdas, self.length_unit_in_meters) + ",",
                  to_string(self.ground_albedo, lambdas, 1.0) + ",",
                  str(cos(self.max_sun_zenith_angle)) + ");",
                  "const vec3 SKY_SPECTRAL_RADIANCE_TO_LUMINANCE = vec3(%f, %f, %f);" % (sky_k_r, sky_k_g, sky_k_b),
                  "const vec3 SUN_SPECTRAL_RADIANCE_TO_LUMINANCE = vec3(%f, %f, %f);" % (sun_k_r, sun_k_g, sun_k_b),
                  functions_glsl]
        return "\n".join(header)

    def Init(self, num_scattering_orders=4):
        resource_manager = CoreManager.instance().resource_manager
        renderer = CoreManager.instance().renderer

        if not self.precompute_illuminance:
            lambdas = [kLambdaR, kLambdaG, kLambdaB]
            luminance_from_radiance = Matrix3()
            self.Precompute(lambdas,
                            luminance_from_radiance,
                            False,
                            num_scattering_orders)
        else:
            num_iterations = (self.num_precomputed_wavelengths + 2) / 3
            dlambda = (kLambdaMax - kLambdaMin) / (3 * num_iterations)

            def coeff(L, component):
                x = CieColorMatchingFunctionTableValue(L, 1)
                y = CieColorMatchingFunctionTableValue(L, 2)
                z = CieColorMatchingFunctionTableValue(L, 3)
                return (XYZ_TO_SRGB[component * 3] * x +
                        XYZ_TO_SRGB[component * 3 + 1] * y +
                        XYZ_TO_SRGB[component * 3 + 2] * z) * dlambda

            for i in range(int(num_iterations)):
                lambdas = [kLambdaMin + (3 * i + 0.5) * dlambda,
                           kLambdaMin + (3 * i + 1.5) * dlambda,
                           kLambdaMin + (3 * i + 2.5) * dlambda]

                luminance_from_radiance = Matrix3()

                luminance_from_radiance[0] = [coeff(lambdas[0], 0), coeff(lambdas[1], 0), coeff(lambdas[2], 0)]
                luminance_from_radiance[1] = [coeff(lambdas[0], 1), coeff(lambdas[1], 1), coeff(lambdas[2], 1)]
                luminance_from_radiance[2] = [coeff(lambdas[0], 2), coeff(lambdas[1], 2), coeff(lambdas[2], 2)]

                self.Precompute(lambdas,
                                luminance_from_radiance,
                                0 < i,
                                num_scattering_orders)

        # Note : recompute compute_transmittance
        # renderer.framebuffer_manager.bind_framebuffer(self.transmittance_texture, depth_texture=None)
        # recompute_transmittance_mi = resource_manager.getMaterialInstance(
        #     'precomputed_scattering.recompute_transmittance',
        #     macros=self.material_instance_macros)
        # recompute_transmittance_mi.use_program()
        # self.quad.bind_vertex_buffer()
        # self.quad.draw_elements()

    def Precompute(self,
                   lambdas,
                   luminance_from_radiance,
                   blend,
                   num_scattering_orders):

        resource_manager = CoreManager.instance().resource_manager
        shader_loader = resource_manager.shader_loader
        renderer = CoreManager.instance().renderer

        shader_name = 'precomputed_scattering.compute_atmosphere_predefine'
        compute_atmosphere_predefine = resource_manager.getShader(shader_name)
        compute_atmosphere_predefine.shader_code = self.glsl_header_factory(lambdas)
        shader_loader.save_resource(shader_name)
        shader_loader.load_resource(shader_name)

        glEnable(GL_BLEND)
        glBlendEquationSeparate(GL_FUNC_ADD, GL_FUNC_ADD)
        glBlendFuncSeparate(GL_ONE, GL_ONE, GL_ONE, GL_ONE)

        self.quad.bind_vertex_buffer()

        # compute_transmittance
        renderer.framebuffer_manager.bind_framebuffer(self.transmittance_texture,
                                                      depth_texture=None)
        glDisablei(GL_BLEND, 0)
        compute_transmittance_mi = resource_manager.getMaterialInstance(
            'precomputed_scattering.compute_transmittance',
            macros=self.material_instance_macros)
        compute_transmittance_mi.use_program()
        self.quad.draw_elements()

        # compute_direct_irradiance
        renderer.framebuffer_manager.bind_framebuffer(self.delta_irradiance_texture,
                                                      self.irradiance_texture,
                                                      depth_texture=None)
        if blend:
            glEnablei(GL_BLEND, 1)
        compute_direct_irradiance_mi = resource_manager.getMaterialInstance(
            'precomputed_scattering.compute_direct_irradiance',
            macros=self.material_instance_macros)
        compute_direct_irradiance_mi.use_program()
        compute_direct_irradiance_mi.bind_uniform_data('transmittance_texture', self.transmittance_texture)
        self.quad.draw_elements()
        glDisablei(GL_BLEND, 0)
        glDisablei(GL_BLEND, 1)

        # compute_single_scattering
        if self.optional_single_mie_scattering_texture is None:
            renderer.framebuffer_manager.bind_framebuffer(self.delta_rayleigh_scattering_texture,
                                                          self.delta_mie_scattering_texture,
                                                          self.scattering_texture,
                                                          depth_texture=None)
        else:
            renderer.framebuffer_manager.bind_framebuffer(self.delta_rayleigh_scattering_texture,
                                                          self.delta_mie_scattering_texture,
                                                          self.scattering_texture,
                                                          self.optional_single_mie_scattering_texture,
                                                          depth_texture=None)
        compute_single_scattering_mi = resource_manager.getMaterialInstance(
            'precomputed_scattering.compute_single_scattering',
            macros=self.material_instance_macros)
        compute_single_scattering_mi.use_program()
        compute_single_scattering_mi.bind_uniform_data('luminance_from_radiance', luminance_from_radiance)
        compute_single_scattering_mi.bind_uniform_data('transmittance_texture', self.transmittance_texture)

        if blend:
            glEnablei(GL_BLEND, 2)
            glEnablei(GL_BLEND, 3)

        for layer in range(SCATTERING_TEXTURE_DEPTH):
            compute_single_scattering_mi.bind_uniform_data("layer", layer)
            self.quad.draw_elements()

        glDisablei(GL_BLEND, 0)
        glDisablei(GL_BLEND, 1)
        glDisablei(GL_BLEND, 2)
        glDisablei(GL_BLEND, 3)

        for scattering_order in range(2, num_scattering_orders+1):
            # compute_scattering_density
            renderer.framebuffer_manager.bind_framebuffer(self.delta_scattering_density_texture, depth_texture=None)
            compute_scattering_density_mi = resource_manager.getMaterialInstance(
                'precomputed_scattering.compute_scattering_density',
                macros=self.material_instance_macros)
            compute_scattering_density_mi.use_program()
            compute_scattering_density_mi.bind_uniform_data('transmittance_texture', self.transmittance_texture)
            compute_scattering_density_mi.bind_uniform_data('single_rayleigh_scattering_texture',
                                                            self.delta_rayleigh_scattering_texture)
            compute_scattering_density_mi.bind_uniform_data('single_mie_scattering_texture',
                                                            self.delta_mie_scattering_texture)
            compute_scattering_density_mi.bind_uniform_data('multiple_scattering_texture',
                                                            self.delta_multiple_scattering_texture)
            compute_scattering_density_mi.bind_uniform_data('irradiance_texture',
                                                            self.delta_irradiance_texture)
            compute_scattering_density_mi.bind_uniform_data('scattering_order', scattering_order)

            for layer in range(SCATTERING_TEXTURE_DEPTH):
                compute_scattering_density_mi.bind_uniform_data('layer', layer)
                self.quad.draw_elements()

            # compute_indirect_irradiance
            renderer.framebuffer_manager.bind_framebuffer(self.delta_irradiance_texture,
                                                          self.irradiance_texture,
                                                          depth_texture=None)
            compute_indirect_irradiance_mi = resource_manager.getMaterialInstance(
                'precomputed_scattering.compute_indirect_irradiance',
                macros=self.material_instance_macros)
            compute_indirect_irradiance_mi.use_program()
            compute_indirect_irradiance_mi.bind_uniform_data('luminance_from_radiance', luminance_from_radiance)
            compute_indirect_irradiance_mi.bind_uniform_data('single_rayleigh_scattering_texture',
                                                             self.delta_rayleigh_scattering_texture)
            compute_indirect_irradiance_mi.bind_uniform_data('single_mie_scattering_texture',
                                                             self.delta_mie_scattering_texture)
            compute_indirect_irradiance_mi.bind_uniform_data('multiple_scattering_texture',
                                                             self.delta_multiple_scattering_texture)
            compute_indirect_irradiance_mi.bind_uniform_data('scattering_order', scattering_order - 1)
            if blend:
                glEnablei(GL_BLEND, 1)
            self.quad.draw_elements()
            glDisablei(GL_BLEND, 0)
            glDisablei(GL_BLEND, 1)

            # compute_multiple_scattering
            renderer.framebuffer_manager.bind_framebuffer(self.delta_multiple_scattering_texture,
                                                          self.scattering_texture,
                                                          depth_texture=None)
            compute_multiple_scattering_mi = resource_manager.getMaterialInstance(
                'precomputed_scattering.compute_multiple_scattering',
                macros=self.material_instance_macros)
            compute_multiple_scattering_mi.use_program()
            compute_multiple_scattering_mi.bind_uniform_data('luminance_from_radiance', luminance_from_radiance)
            compute_multiple_scattering_mi.bind_uniform_data('transmittance_texture', self.transmittance_texture)
            compute_multiple_scattering_mi.bind_uniform_data('scattering_density_texture',
                                                             self.delta_scattering_density_texture)
            if blend:
                glEnablei(GL_BLEND, 1)
            for layer in range(SCATTERING_TEXTURE_DEPTH):
                compute_multiple_scattering_mi.bind_uniform_data('layer', layer)
                self.quad.draw_elements()
            glDisablei(GL_BLEND, 0)
            glDisablei(GL_BLEND, 1)
