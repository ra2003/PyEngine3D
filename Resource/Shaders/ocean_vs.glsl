#include "scene_constants.glsl"

struct VERTEX_OUTPUT
{
    vec2 tex_coord;
    vec3 position;
};

uniform float height;

#ifdef GL_VERTEX_SHADER
layout (location = 0) in vec3 vs_in_position;
layout (location = 1) in vec4 vs_in_color;
layout (location = 2) in vec3 vs_in_normal;
layout (location = 3) in vec3 vs_in_tangent;
layout (location = 4) in vec2 vs_in_tex_coord;

layout (location = 0) out VERTEX_OUTPUT vs_output;

void main() {
    vs_output.tex_coord = vs_in_tex_coord;
    vs_output.position = vs_in_position;
    vs_output.position.y += height;
    vs_output.position.z -= 1.0;

    vec4 proj_pos = PROJECTION * VIEW_ORIGIN * vec4(vs_output.position, 1.0);

    gl_Position = proj_pos;
}
#endif // GL_VERTEX_SHADER