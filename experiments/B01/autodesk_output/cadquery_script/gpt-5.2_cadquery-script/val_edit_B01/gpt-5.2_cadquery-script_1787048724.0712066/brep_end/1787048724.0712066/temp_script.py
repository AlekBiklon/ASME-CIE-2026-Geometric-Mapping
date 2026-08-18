def my_cad_function(args):
    import os
    import cadquery as cq

    # --- locate STEP path ---
    step_path = None
    if isinstance(args, dict):
        for k in ["input_file", "brep_start_path_step", "step_file", "step_path"]:
            if k in args and args[k]:
                step_path = os.path.expanduser(str(args[k]))
                break
    if not step_path:
        step_path = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/SUJ2G2UMJQR7PMBX_1757677066.6712623.step"

    if not os.path.exists(step_path):
        print("STEP path does not exist:", step_path)
        return None

    wp = cq.importers.importStep(step_path)
    shape = wp.val() if hasattr(wp, "val") else wp

    # --- Fusion selection event data ---
    # Fusion event appears to be in cm (and cm^2); STEP model is in mm.
    raw_pt = cq.Vector(-0.9689042506737217, -0.040016009795494537, 1.75)
    raw_area = 2.5201549772318073  # cm^2

    scale = 10.0  # cm -> mm
    target_pt = cq.Vector(raw_pt.x * scale, raw_pt.y * scale, raw_pt.z * scale)
    target_area = raw_area * (scale ** 2)  # mm^2

    print(f"Loaded STEP: {step_path}")
    try:
        bb = shape.BoundingBox()
        print(
            f"Model BBox (mm): x[{bb.xmin:.3f},{bb.xmax:.3f}] y[{bb.ymin:.3f},{bb.ymax:.3f}] z[{bb.zmin:.3f},{bb.zmax:.3f}]"
        )
    except Exception:
        pass
    print(f"Target point (mm): ({target_pt.x:.4f},{target_pt.y:.4f},{target_pt.z:.4f})")
    print(f"Target face area (mm^2): ~{target_area:.3f}")

    faces = shape.Faces()

    # --- choose best matching face using true point-to-face distance + area match ---
    chosen_face = None
    chosen_dist = None

    try:
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        have_extrema = True
    except Exception:
        have_extrema = False

    if have_extrema:
        vtx = cq.Vertex.makeVertex(target_pt.x, target_pt.y, target_pt.z)
        best_score = 1e99
        for f in faces:
            try:
                dss = BRepExtrema_DistShapeShape(vtx.wrapped, f.wrapped)
                dss.Perform()
                d = float(dss.Value())
            except Exception:
                continue

            try:
                a = float(f.Area())
                area_term = abs(a - target_area)
            except Exception:
                area_term = 0.0

            # prioritize being on/near the face, then area agreement
            score = d * 1e6 + area_term
            if score < best_score:
                best_score = score
                chosen_face = f
                chosen_dist = d

    if chosen_face is None:
        chosen_face = cq.Workplane(obj=shape).faces(cq.selectors.NearestToPointSelector(target_pt)).val()
        chosen_dist = None

    fc = chosen_face.Center()
    try:
        fa = float(chosen_face.Area())
    except Exception:
        fa = None

    if chosen_dist is not None:
        print(f"Chosen face dist to target (mm): {chosen_dist:.6f}")
    print(f"Chosen face center (mm): ({fc.x:.4f},{fc.y:.4f},{fc.z:.4f})" + (f"  area={fa:.3f} mm^2" if fa is not None else ""))

    # --- project target point to the actual surface and compute surface normal there ---
    proj_pt = target_pt
    n = None

    try:
        from OCP.BRep import BRep_Tool
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        from OCP.GeomLProp import GeomLProp_SLProps
        from OCP.gp import gp_Pnt

        surf = BRep_Tool.Surface(chosen_face.wrapped)
        projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(target_pt.x, target_pt.y, target_pt.z), surf)
        if projector.NbPoints() > 0:
            p = projector.NearestPoint()
            u, v = projector.LowerDistanceParameters()
            proj_pt = cq.Vector(p.X(), p.Y(), p.Z())

            props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
            ngp = props.Normal()
            n = cq.Vector(ngp.X(), ngp.Y(), ngp.Z())
    except Exception as e:
        print("Surface projection/normal failed; falling back to face workplane normal. Error:", e)

    if n is None:
        # fallback: use face workplane normal
        face_wp = cq.Workplane(obj=shape).faces(cq.selectors.NearestToPointSelector(fc))
        pl = face_wp.workplane(centerOption="CenterOfMass").plane
        n = cq.Vector(pl.zDir.x, pl.zDir.y, pl.zDir.z)

    # normalize
    ln = (n.x * n.x + n.y * n.y + n.z * n.z) ** 0.5
    if ln < 1e-9:
        print("Invalid normal; returning original shape")
        return shape
    n = cq.Vector(n.x / ln, n.y / ln, n.z / ln)

    print(f"Hole point on surface (mm): ({proj_pt.x:.4f},{proj_pt.y:.4f},{proj_pt.z:.4f})")
    print(f"Hole axis direction: ({n.x:.4f},{n.y:.4f},{n.z:.4f})")

    # --- cut a robust long cylinder (Ø2mm) through the part ---
    bb = shape.BoundingBox()
    diag = (bb.xlen ** 2 + bb.ylen ** 2 + bb.zlen ** 2) ** 0.5
    cut_len = max(120.0, diag * 6.0)

    start_pt = proj_pt - n.multiply(cut_len / 2.0)
    cyl = cq.Solid.makeCylinder(1.0, cut_len, pnt=start_pt, dir=n)  # r=1mm => Ø2mm

    v0 = None
    try:
        v0 = float(shape.Volume())
    except Exception:
        pass

    result = shape.cut(cyl)

    v1 = None
    try:
        v1 = float(result.Volume())
    except Exception:
        pass

    if v0 is not None and v1 is not None:
        print(f"Volume before (mm^3): {v0:.3f}")
        print(f"Volume after  (mm^3): {v1:.3f}")
        print(f"Volume delta (mm^3): {v1 - v0:.3f}")

    print("Added 2.0mm diameter reset-button access hole.")
    return result
