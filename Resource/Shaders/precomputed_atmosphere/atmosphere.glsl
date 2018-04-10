#include "blending.glsl"
#include "utility.glsl"
#include "precomputed_atmosphere/atmosphere_predefine.glsl"
#include "precomputed_atmosphere/atmosphere_vs.glsl"

uniform sampler2D texture_shadow;
uniform sampler2D texture_linear_depth;
uniform sampler2D texture_normal;

uniform float cloud_base_tiling;
uniform float cloud_base_contrast;
uniform float cloud_base_coverage;
uniform float cloud_detail_tiling;
uniform float cloud_detail_contrast;
uniform float cloud_detail_coverage;
uniform float cloud_altitude;
uniform float cloud_height;

#ifdef MATERIAL_COMPONENTS
    uniform sampler3D texture_noise_01;
    uniform sampler3D texture_noise_02;
#endif

#ifdef GL_FRAGMENT_SHADER
in vec3 view_ray;
in vec2 uv;
layout(location = 0) out vec4 color;


void GetSceneRadiance(
    const in AtmosphereParameters atmosphere,
    float dist, vec3 eye_direction, float scene_shadow_length,
    out vec3 sun_irradiance, out vec3 sky_irradiance, out vec3 in_scatter)
{
    vec3 sun_direction = LIGHT_DIRECTION.xyz;
    vec3 relative_camera_pos = CAMERA_POSITION.xyz * atmosphere_ratio;
    vec3 relative_point = relative_camera_pos + eye_direction.xyz * max(NEAR_FAR.x, dist) * atmosphere_ratio;
    vec3 N = normalize(relative_point - earth_center);

    sun_irradiance = GetSunAndSkyIrradiance(
        atmosphere, relative_point.xyz - earth_center, N, sun_direction, sky_irradiance);

    vec3 transmittance;
    in_scatter = GetSkyRadianceToPoint(atmosphere, relative_camera_pos - earth_center,
        relative_point.xyz - earth_center, scene_shadow_length, sun_direction, transmittance);

    sun_irradiance *= transmittance / PI;
    sky_irradiance *= transmittance / PI;
}


float get_cloud_density(vec3 noise_01_scale, vec3 noise_02_scale, vec3 uvw, vec3 cloud_speed, float weight)
{
    uvw.xy += CAMERA_POSITION.xz;

    float noise_02 = texture(texture_noise_02, uvw * noise_02_scale + cloud_speed * 0.5).x;
    noise_02 = saturate(Contrast((noise_02 - 1.0 + cloud_base_coverage) * weight, cloud_base_contrast));

    float noise_01 = texture(texture_noise_01, uvw * noise_01_scale + cloud_speed * cloud_detail_tiling / cloud_base_tiling).x * weight;
    noise_01 = saturate(Contrast((noise_01 - 1.0 + cloud_detail_coverage) * weight, cloud_detail_contrast));

    return noise_01 * noise_02;
}

void main()
{
    float scene_linear_depth = textureLod(texture_linear_depth, uv, 0.0).x;

    if(scene_linear_depth < NEAR_FAR.y)
    {
        discard;
    }

    color = vec4(0.0, 0.0, 0.0, 1.0);
    vec3 camera = CAMERA_POSITION.xyz * atmosphere_ratio;
    vec3 sun_direction = LIGHT_DIRECTION.xyz;
    vec3 eye_direction = normalize(view_ray);

    // Scene
    float scene_shadow_length = GetSceneShadowLength(scene_linear_depth, eye_direction, texture_shadow);

    // Sky
    vec3 transmittance;
    vec3 radiance = GetSkyRadiance(
        ATMOSPHERE, camera - earth_center, eye_direction, scene_shadow_length, sun_direction, transmittance);

    // Sun
    if (render_sun && dot(eye_direction, sun_direction) > sun_size.y)
    {
        radiance = radiance + transmittance * GetSolarRadiance(ATMOSPHERE);
    }

    // Cloud
    vec4 cloud = vec4(0.0);
    const float min_dist = 1000.0;
    const float far_dist = NEAR_FAR.y * 4.0;

    vec3 earth_center_pos = earth_center / atmosphere_ratio;

    // distance from earch center
    const float cloud_bottom_dist = cloud_altitude - earth_center_pos.y;
    const float cloud_top_dist = cloud_bottom_dist + cloud_height;
    float altitude_diff = cloud_altitude - CAMERA_POSITION.y;
    const bool in_the_cloud = -cloud_height < altitude_diff && altitude_diff < 0.0;

    {
        // relative ray march start pos from the camera
        vec3 ray_start_pos;
        float hit_dist;

        if(in_the_cloud)
        {
            // be in clouds
            ray_start_pos = vec3(0.0, 0.0, 0.0);
            hit_dist = 0.0;
        }
        else
        {
            // https://en.wikipedia.org/wiki/Line%E2%80%93sphere_intersection

            vec3 to_origin = vec3(0.0, CAMERA_POSITION.y, 0.0) - earth_center_pos;
            float c = pow(dot(eye_direction, to_origin), 2.0) - dot(to_origin, to_origin);

            if(cloud_altitude < CAMERA_POSITION.y)
            {
                // above the sky
                if(eye_direction.y < 0.0)
                {
                    // look down
                    c = -sqrt(c + cloud_top_dist * cloud_top_dist);
                }
                else
                {
                    // look up, discard
                    discard;
                }
            }
            else
            {
                // under the sky
                float r = cloud_altitude - earth_center_pos.y;
                c = sqrt(c + cloud_bottom_dist * cloud_bottom_dist);
            }

            hit_dist = -dot(eye_direction, to_origin) + c;
            ray_start_pos = eye_direction * hit_dist;
        }

        // Atmosphere
        vec3 scene_in_scatter;
        vec3 scene_sun_irradiance;
        vec3 scene_sky_irradiance;
        {
            float scene_shadow_length = 0.0;
            GetSceneRadiance(
                ATMOSPHERE, hit_dist, -eye_direction, scene_shadow_length,
                scene_sun_irradiance, scene_sky_irradiance, scene_in_scatter);
            scene_sun_irradiance = scene_sun_irradiance * exposure;
            scene_sky_irradiance *= exposure;
            scene_in_scatter *= exposure;
        }

        // apply altitude of camera
        ray_start_pos.y += CAMERA_POSITION.y;

        const vec3 light_color = LIGHT_COLOR.xyz * (scene_sun_irradiance + scene_sky_irradiance);

        cloud.xyz = light_color;
        cloud.w = 0.0;

        if(0.0 <= hit_dist && hit_dist < far_dist)
        {
            int march_count = 64;
            const int light_march_count = 3;
            const float cloud_absorption = min(1.0, 3.0 / float(march_count));
            const float light_absorption = min(1.0, 3.0 / float(light_march_count));
            const vec3 cloud_speed = vec3(0.01, 0.01, 0.0) * TIME;
            vec3 noise_01_scale = textureSize(texture_noise_01, 0);
            vec3 noise_02_scale = textureSize(texture_noise_01, 0);
            noise_01_scale = max(noise_01_scale.x, max(noise_01_scale.y, noise_01_scale.z)) / noise_01_scale;
            noise_01_scale *= cloud_detail_tiling;
            noise_02_scale = max(noise_02_scale.x, max(noise_02_scale.y, noise_02_scale.z)) / noise_02_scale;
            noise_02_scale *= cloud_base_tiling;

            // march step by distance
            float march_step = cloud_height / max(0.1, abs(eye_direction.y)) / float(march_count);
            //float march_step = cloud_height / float(march_count);
            float light_march_step = cloud_height / float(march_count);

            for(int i=0; i<march_count; ++i)
            {
                vec3 ray_pos;
                ray_pos = ray_start_pos.xyz + eye_direction.xyz * float(i) * march_step;

                // fade top and bottom
                float relative_altitude = length(ray_pos - earth_center_pos.xyz) - cloud_bottom_dist;

                if(0 != i && (cloud_height < relative_altitude || relative_altitude < 0.0))
                {
                    break;
                }

                float fade = saturate(relative_altitude / cloud_height);
                fade = 1.0 - pow(abs(fade * 2.0 - 1.0), 3.0);

                float cloud_density = get_cloud_density(noise_01_scale, noise_02_scale, ray_pos.xzy, cloud_speed, fade);

                float light_intensity = 1.0;
                for(int j=0; j<light_march_count; ++j)
                {
                    vec3 light_pos = ray_pos + sun_direction * float(light_march_count - j) * march_step;
                    relative_altitude = length(light_pos.xyz - earth_center_pos.xyz) - cloud_bottom_dist;

                    if(cloud_height < relative_altitude || relative_altitude < 0.0)
                    {
                        continue;
                    }

                    fade = 1.0 - pow(abs(saturate(relative_altitude / cloud_height) * 2.0 - 1.0), 3.0);

                    float light_density = get_cloud_density(noise_01_scale, noise_02_scale, light_pos.xzy, cloud_speed, fade);

                    light_intensity *= 1.0 - light_density * light_absorption;

                    if(light_intensity <= 0.01)
                    {
                        break;
                    }
                }

                cloud.w = clamp(cloud.w + cloud_density * (1.0 - cloud_absorption), 0.0, 1.0);
                cloud.xyz = light_color * light_intensity;
                if(1.0 <= cloud.w)
                {
                    break;
                }
            }

            float dist_fade = clamp(1.0 - (hit_dist - min_dist) / (far_dist - min_dist), 0.0, 1.0);
            cloud.w *= clamp(dist_fade, 0.0, 1.0);
        }
        cloud.xyz += scene_in_scatter;
    }

    color.xyz = mix(radiance * exposure, cloud.xyz, cloud.w);
    color.w = 1.0;
    color = max(color, 0.0);
}
#endif
