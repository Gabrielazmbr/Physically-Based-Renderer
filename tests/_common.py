import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mitsuba as mi
mi.set_variant("llvm_ad_rgb")

from integrators.path_tracer import PathTracer
from bsdfs.principled import PrincipledBSDF
from cameras.thin_lens_camera import ThinLensCamera
from emitters.envmap import CustomEnvmap

mi.register_integrator("path_tracer", lambda props: PathTracer(props))
mi.register_bsdf("principled_bsdf", lambda props: PrincipledBSDF(props))
mi.register_sensor("thinlens_probe", lambda props: ThinLensCamera(props))
mi.register_emitter("custom_envmap", lambda props: CustomEnvmap(props))
