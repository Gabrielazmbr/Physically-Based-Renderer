import mitsuba as mi

mi.set_variant('llvm_ad_rgb')

# Render the built-in Cornell Box
img = mi.render(mi.load_dict(mi.cornell_box()))

# Save it
mi.Bitmap(img).write('cornell_box.exr')
print("Success — Cornell Box rendered to cornell_box.exr")
