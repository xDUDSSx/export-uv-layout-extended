	# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####


bl_info = {
	"name": "Export UV Layout Extended",
	"author": "Campbell Barton, Matt Ebb, DUDSS",
	"version": (1, 1, 1),
	"blender": (3, 0, 1),
	"location": "Image-Window > UVs > Export UV Layout (Extended)",
	"description": "Export the UV layout as a 2D graphic to PNG with expanded options (outline/fill only, colors, ignoring materials, disable AA, saving state)",
	"warning": "",
	"doc_url": "{BLENDER_MANUAL_URL}/addons/import_export/mesh_uv_layout.html",
	"support": 'OFFICIAL',
	"category": "Import-Export",
}

import bpy
import gpu
import bgl
from mathutils import Vector, Matrix
from mathutils.geometry import tessellate_polygon
from gpu_extras.batch import batch_for_shader

def export(filepath, face_data, colors, width, height, opacity, draw_fill, draw_outline, outline_color, clear_color, enable_aa):
	offscreen = gpu.types.GPUOffScreen(width, height)
	offscreen.bind()

	try:
		bgl.glClearColor(clear_color[0], clear_color[1], clear_color[2], clear_color[3])
		bgl.glClear(bgl.GL_COLOR_BUFFER_BIT)
		draw_image(face_data, opacity, draw_fill, draw_outline, outline_color, enable_aa)

		pixel_data = get_pixel_data_from_current_back_buffer(width, height)
		save_pixels(filepath, pixel_data, width, height)
	finally:
		offscreen.unbind()
		offscreen.free()

def draw_image(face_data, opacity, draw_fill, draw_outline, outline_color, enable_aa):
	bgl.glLineWidth(1)
	bgl.glEnable(bgl.GL_BLEND)
	if enable_aa:
		bgl.glEnable(bgl.GL_LINE_SMOOTH)
		bgl.glHint(bgl.GL_LINE_SMOOTH_HINT, bgl.GL_NICEST)
	bgl.glLineWidth(1.0);

	with gpu.matrix.push_pop():
		gpu.matrix.load_matrix(get_normalize_uvs_matrix())
		gpu.matrix.load_projection_matrix(Matrix.Identity(4))

		if draw_fill: draw_background_colors(face_data, opacity)
		if draw_outline: draw_lines(face_data, outline_color)

	bgl.glDisable(bgl.GL_BLEND)
	if enable_aa:
		bgl.glDisable(bgl.GL_LINE_SMOOTH)

def get_normalize_uvs_matrix():
	'''matrix maps x and y coordinates from [0, 1] to [-1, 1]'''
	matrix = Matrix.Identity(4)
	matrix.col[3][0] = -1
	matrix.col[3][1] = -1
	matrix[0][0] = 2
	matrix[1][1] = 2
	return matrix

def draw_background_colors(face_data, opacity):
	coords = [uv for uvs, _ in face_data for uv in uvs]
	colors = [(*color, opacity) for uvs, color in face_data for _ in range(len(uvs))]

	indices = []
	offset = 0
	for uvs, _ in face_data:
		triangles = tessellate_uvs(uvs)
		indices.extend([index + offset for index in triangle] for triangle in triangles)
		offset += len(uvs)

	shader = gpu.shader.from_builtin('2D_FLAT_COLOR')
	batch = batch_for_shader(shader, 'TRIS',
		{"pos" : coords,
		 "color" : colors},
		indices=indices)
	batch.draw(shader)

def tessellate_uvs(uvs):
	return tessellate_polygon([uvs])

def draw_lines(face_data, color):
	coords = []
	for uvs, _ in face_data:
		for i in range(len(uvs)):
			start = uvs[i]
			end = uvs[(i+1) % len(uvs)]
			coords.append((start[0], start[1]))
			coords.append((end[0], end[1]))

	shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
	batch = batch_for_shader(shader, 'LINES', {"pos" : coords})
	shader.bind()
	shader.uniform_float("color", color)
	batch.draw(shader)

#    vertices = (
#    (0.1, 0.1), (0.3, 0.1),
#    (0.1, 0.2), (0.3, 0.2))
#    indices = (
#        (0, 1, 2), (2, 1, 3))
#    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
#    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
#    shader.bind()
#    shader.uniform_float("color", color)
#    batch.draw(shader)

def draw():
	shader.bind()
	shader.uniform_float("color", (0, 0.5, 0.5, 1.0))
	batch.draw(shader)

def get_pixel_data_from_current_back_buffer(width, height):
	buffer = bgl.Buffer(bgl.GL_BYTE, width * height * 4)
	bgl.glReadBuffer(bgl.GL_BACK)
	bgl.glReadPixels(0, 0, width, height, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, buffer)
	return buffer

def save_pixels(filepath, pixel_data, width, height):
	image = bpy.data.images.new("temp", width, height, alpha=True)
	image.filepath = filepath
	image.pixels = [v / 255 for v in pixel_data]
	image.save()
	bpy.data.images.remove(image)

#################################################################

import os
from bpy.types import Scene
from bpy.props import (
	StringProperty,
	BoolProperty,
	EnumProperty,
	IntVectorProperty,
	FloatProperty,
	FloatVectorProperty,
)

class ExportUVLayoutExtendedData(bpy.types.PropertyGroup):
	filepath: StringProperty(
		subtype='FILE_PATH',
		default="",
	)
	export_all: BoolProperty(
		name="All UVs",
		description="Export all UVs in this mesh (not just visible ones)",
		default=False,
	)
	modified: BoolProperty(
		name="Modified",
		description="Exports UVs from the modified mesh",
		default=False,
	)
	mode: EnumProperty(
		items=(
			('PNG', "PNG Image (.png)",
			 "Export the UV layout to a bitmap image"),
		),
		name="Format",
		description="File format to export the UV layout to",
		default='PNG',
	)
	size: IntVectorProperty(
		size=2,
		default=(1024, 1024),
		min=8, max=32768,
		description="Dimensions of the exported file",
	)
	opacity: FloatProperty(
		name="Fill Opacity",
		min=0.0, max=1.0,
		default=0.25,
		description="Set amount of opacity for exported UV layout",
	)
	# For the file-selector.
	check_existing: BoolProperty(
		default=True,
		options={'HIDDEN'},
	)

	# Extensions:

	draw_fill: BoolProperty(
		name="Draw fill",
		default=True,
	)
	default_fill_color: FloatVectorProperty(
		name="Fill Color",
		subtype='COLOR',
		default=(0.8, 0.8, 0.8),
		min=0.0, max=1.0,
		description="color picker"
	)
	ignore_materials: BoolProperty(
		name="Ignore materials",
		description="By default, fill color is based on assigned material viewport color. This colors all faces with the default color.",
		default=False,
	)
	draw_outline: BoolProperty(
		name="Draw Outline",
		default=True,
	)
	outline_color: FloatVectorProperty(
		name="Outline Color",
		subtype='COLOR',
		size=4,
		default=(0.0, 0.0, 0.0, 1.0),
		min=0.0, max=1.0,
		description="Color of the outline, black by default."
	)
	background_color: FloatVectorProperty(
		name="Background Color",
		subtype='COLOR',
		size=4,
		default=(0.0, 0.0, 0.0, 0.0),
		min=0.0, max=1.0,
		description="Color of the image background, transparent by default."
	)
	enable_aa: BoolProperty(
		name="Line Anti Aliasing",
		default=True,
	)

class ExportUVLayoutExtended(bpy.types.Operator):
	"""Export UV layout to file, extended"""

	bl_idname = "uv.export_layout_extended"
	bl_label = "Export UV Layout Extended"
	bl_options = {'REGISTER', 'UNDO'}

	filepath: StringProperty(
		subtype='FILE_PATH',
	)
	export_all: BoolProperty(
		name="All UVs",
		description="Export all UVs in this mesh (not just visible ones)",
		default=False,
	)
	modified: BoolProperty(
		name="Modified",
		description="Exports UVs from the modified mesh",
		default=False,
	)
	mode: EnumProperty(
		items=(
			('PNG', "PNG Image (.png)",
			 "Export the UV layout to a bitmap image"),
		),
		name="Format",
		description="File format to export the UV layout to",
		default='PNG',
	)
	size: IntVectorProperty(
		size=2,
		default=(1024, 1024),
		min=8, max=32768,
		description="Dimensions of the exported file",
	)
	# For the file-selector.
	check_existing: BoolProperty(
		default=True,
		options={'HIDDEN'},
	)

	# Extensions:

	draw_fill: BoolProperty(
		name="Draw fill",
		default=True,
	)
	opacity: FloatProperty(
		name="Fill Opacity",
		min=0.0, max=1.0,
		default=0.25,
	)
	default_fill_color: FloatVectorProperty(
		name="Fill Color",
		subtype='COLOR',
		default=(0.8, 0.8, 0.8),
		min=0.0, max=1.0,
		description="Default fill color, 0.8 gray by default."
	)
	draw_outline: BoolProperty(
		name="Draw Outline",
		default=True,
	)
	outline_color: FloatVectorProperty(
		name="Outline Color",
		subtype='COLOR',
		size=4,
		default=(0.0, 0.0, 0.0, 1.0),
		min=0.0, max=1.0,
		description="Color of the outline, black by default."
	)
	background_color: FloatVectorProperty(
		name="Background Color",
		subtype='COLOR',
		size=4,
		default=(0.0, 0.0, 0.0, 0.0),
		min=0.0, max=1.0,
		description="Color of the image background, transparent by default."
	)
	enable_aa: BoolProperty(
		name="Line Anti Aliasing",
		default=True,
	)
	ignore_materials: BoolProperty(
		name="Ignore materials",
		description="By default, fill color is based on assigned material viewport color. This colors all faces with the default color.",
		default=False,
	)

	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return obj is not None and obj.type == 'MESH' and obj.data.uv_layers

	def invoke(self, context, event):
		self.load_data(context.scene.export_uv_layout_extended_data)

		if self.size == (1024, 1024): self.size = self.get_image_size(context)
		if self.filepath == "": self.filepath = self.get_default_file_name(context) + "." + self.mode.lower()
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}

	def get_default_file_name(self, context):
		AMOUNT = 3
		objects = list(self.iter_objects_to_export(context))
		name = " ".join(sorted([obj.name for obj in objects[:AMOUNT]]))
		if len(objects) > AMOUNT:
			name += " and more"
		return name

	def check(self, context):
		if any(self.filepath.endswith(ext) for ext in (".png")):
			self.filepath = self.filepath[:-4]

		ext = "." + self.mode.lower()
		self.filepath = bpy.path.ensure_ext(self.filepath, ext)
		return True

	def execute(self, context):
		obj = context.active_object
		is_editmode = (obj.mode == 'EDIT')
		if is_editmode:
			bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

		filepath = self.filepath
		filepath = bpy.path.ensure_ext(filepath, "." + self.mode.lower())

		meshes = list(self.iter_meshes_to_export(context))
		polygon_data = list(self.iter_polygon_data_to_draw(context, meshes))
		different_colors = set(color for _, color in polygon_data)
		if self.modified:
		  depsgraph = context.evaluated_depsgraph_get()
		  for obj in self.iter_objects_to_export(context):
			  obj_eval = obj.evaluated_get(depsgraph)
			  obj_eval.to_mesh_clear()

		export(filepath, polygon_data, different_colors, self.size[0], self.size[1], self.opacity, self.draw_fill, self.draw_outline, tuple(self.outline_color), tuple(self.background_color), self.enable_aa)

		if is_editmode:
			bpy.ops.object.mode_set(mode='EDIT', toggle=False)

		self.save_data(context.scene.export_uv_layout_extended_data)
		return {'FINISHED'}

	def iter_meshes_to_export(self, context):
		depsgraph = context.evaluated_depsgraph_get()
		for obj in self.iter_objects_to_export(context):
			if self.modified:
				yield obj.evaluated_get(depsgraph).to_mesh()
			else:
				yield obj.data

	@staticmethod
	def iter_objects_to_export(context):
		for obj in {*context.selected_objects, context.active_object}:
			if obj.type != 'MESH':
				continue
			mesh = obj.data
			if mesh.uv_layers.active is None:
				continue
			yield obj

	@staticmethod
	def currently_image_image_editor(context):
		return isinstance(context.space_data, bpy.types.SpaceImageEditor)

	def get_currently_opened_image(self, context):
		if not self.currently_image_image_editor(context):
			return None
		return context.space_data.image

	def get_image_size(self, context):
		# fallback if not in image context
		image_width = self.size[0]
		image_height = self.size[1]

		# get size of "active" image if some exist
		image = self.get_currently_opened_image(context)
		if image is not None:
			width, height = image.size
			if width and height:
				image_width = width
				image_height = height

		return image_width, image_height

	def iter_polygon_data_to_draw(self, context, meshes):
		for mesh in meshes:
			uv_layer = mesh.uv_layers.active.data
			for polygon in mesh.polygons:
				if self.export_all or polygon.select:
					start = polygon.loop_start
					end = start + polygon.loop_total
					uvs = tuple(tuple(uv.uv) for uv in uv_layer[start:end])
					if self.ignore_materials:
						yield (uvs, tuple(self.default_fill_color))
					else:
						yield (uvs, self.get_polygon_color(mesh, polygon, self.default_fill_color))

	@staticmethod
	def get_polygon_color(mesh, polygon, default):
		if polygon.material_index < len(mesh.materials):
			material = mesh.materials[polygon.material_index]
			if material is not None:
				return tuple(material.diffuse_color)[:3]
		return tuple(default)

	def load_data(self, data):
		self.filepath           = data.filepath
		self.export_all         = data.export_all
		self.modified           = data.modified
		self.mode               = data.mode
		self.size               = data.size
		self.opacity            = data.opacity
		self.check_existing     = data.check_existing

		self.draw_fill          = data.draw_fill
		self.default_fill_color = data.default_fill_color
		self.ignore_materials   = data.ignore_materials
		self.draw_outline       = data.draw_outline
		self.outline_color      = data.outline_color
		self.background_color   = data.background_color
		self.enable_aa          = data.enable_aa

	def save_data(self, data):
		data.filepath           = self.filepath
		data.export_all         = self.export_all
		data.modified           = self.modified
		data.mode               = self.mode
		data.size               = self.size
		data.opacity            = self.opacity
		data.check_existing     = self.check_existing

		data.draw_fill          = self.draw_fill
		data.default_fill_color = self.default_fill_color
		data.ignore_materials   = self.ignore_materials
		data.draw_outline       = self.draw_outline
		data.outline_color      = self.outline_color
		data.background_color   = self.background_color
		data.enable_aa          = self.enable_aa


def menu_func(self, context):
	self.layout.operator(ExportUVLayoutExtended.bl_idname)


def register():
	bpy.utils.register_class(ExportUVLayoutExtendedData)
	bpy.utils.register_class(ExportUVLayoutExtended)

	Scene.export_uv_layout_extended_data = bpy.props.PointerProperty(type=ExportUVLayoutExtendedData)
	del bpy.context.scene['export_uv_layout_extended_data'] # Reset to defaults after restart

	bpy.types.IMAGE_MT_uvs.append(menu_func)


def unregister():
	bpy.utils.unregister_class(ExportUVLayoutExtended)
	bpy.types.IMAGE_MT_uvs.remove(menu_func)


if __name__ == "__main__":
	register()
