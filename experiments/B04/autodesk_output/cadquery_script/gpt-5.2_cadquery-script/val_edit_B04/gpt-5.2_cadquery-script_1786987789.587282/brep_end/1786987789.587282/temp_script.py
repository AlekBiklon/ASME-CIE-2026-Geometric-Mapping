def my_cad_function(args):
    import os, glob
    import cadquery as cq

    def _norm(p):
        if not p:
            return None
        return os.path.normpath(os.path.expanduser(p))

    def _find_step_path():
        # Primary (runner)
        if args.get("input_file"):
            p = _norm(args.get("input_file"))
            if p and os.path.exists(p) and p.lower().endswith((".step", ".stp")):
                return p

        # Alternate keys
        for k in ("brep_start_path_step", "step_path", "model_path", "input_step"):
            if args.get(k):
                p = _norm(args.get(k))
                if p and os.path.exists(p) and p.lower().endswith((".step", ".stp")):
                    return p

        # Task-info fallbacks (harmless if not present)
        for p0 in (
            r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/ZK22J6VYRKQ2RTFD_1758276130.7397902.step",
            r"C:\\PROGRAMING_PYTHON\\2026-08-14_ASME_Hackathon_2026\\neuralCAD-Edit-data\\edit_192_external\\breps\\ZK22J6VYRKQ2RTFD_1758276130.7397902.step",
        ):
            p = _norm(p0)
            if p and os.path.exists(p):
                return p

        # Search in output_dir/cwd
        search_dirs = []
        if args.get("output_dir"):
            search_dirs.append(_norm(args.get("output_dir")))
        search_dirs.append(os.getcwd())

        found = []
        for d in [sd for sd in search_dirs if sd and os.path.isdir(sd)]:
            found += glob.glob(os.path.join(d, "**", "*.step"), recursive=True)
            found += glob.glob(os.path.join(d, "**", "*.stp"), recursive=True)
        if found:
            found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return _norm(found[0])

        return None

    step_path = _find_step_path()
    if not step_path or not os.path.exists(step_path):
        raise FileNotFoundError(f"STEP input file not found. input_file={args.get('input_file')} resolved={step_path}")

    model_wp = cq.importers.importStep(step_path)
    shape = model_wp.val() if hasattr(model_wp, "val") else model_wp

    bb = shape.BoundingBox()
    rx, ry, rz = (bb.xmax - bb.xmin), (bb.ymax - bb.ymin), (bb.zmax - bb.zmin)
    # Assume the nipple points along the model's longest axis (this file is Y-up in earlier debug)
    axis = max([(rx, "X"), (ry, "Y"), (rz, "Z")], key=lambda t: t[0])[1]

    print(f"Loaded STEP: {step_path}")
    print(f"Overall BBox: x[{bb.xmin:.3f},{bb.xmax:.3f}] y[{bb.ymin:.3f},{bb.ymax:.3f}] z[{bb.zmin:.3f},{bb.zmax:.3f}]")
    print(f"Axis extents: rx={rx:.3f} ry={ry:.3f} rz={rz:.3f} -> drill axis assumed: {axis}")

    solids = list(shape.Solids() or [])
    print(f"Solid count: {len(solids)}")

    # Choose nipple/top solid: solids that reach global top along axis; among them smallest volume.
    def top_of(b, ax):
        return {"X": b.xmax, "Y": b.ymax, "Z": b.zmax}[ax]

    global_top = top_of(bb, axis)
    top_tol = 2.0  # mm

    candidates = []
    for i, s in enumerate(solids):
        sbb = s.BoundingBox()
        if abs(top_of(sbb, axis) - global_top) <= top_tol:
            try:
                vol = s.Volume()
            except Exception:
                vol = 1e99
            candidates.append((vol, i, s, sbb))

    if candidates:
        candidates.sort(key=lambda t: t[0])
        vol0, idx, nipple_solid, nbb = candidates[0]
        print(f"Nipple solid chosen: index={idx}, vol={vol0:.3f}, top={top_of(nbb,axis):.3f}")
    else:
        # Fallback: highest-top solid
        if solids:
            nipple_solid = max(solids, key=lambda s: top_of(s.BoundingBox(), axis))
            nbb = nipple_solid.BoundingBox()
            print("Warning: no top candidates; using highest-top solid as nipple")
        else:
            nipple_solid = None
            nbb = None

    # Determine hole center robustly:
    # Using vertices *slightly below* the absolute top avoids picking a rim/edge point.
    def compute_centerline_point(solid, sbb, ax):
        if solid is None:
            return bb.center

        t = top_of(sbb, ax)
        band_low = t - 2.0
        band_high = t - 0.2
        pts = []
        try:
            for v in list(solid.Vertices() or []):
                p = v.Center()
                val = {"X": p.x, "Y": p.y, "Z": p.z}[ax]
                if band_low <= val <= band_high:
                    pts.append(p)
        except Exception:
            pts = []

        if pts:
            cx = sum(p.x for p in pts) / len(pts)
            cy = sum(p.y for p in pts) / len(pts)
            cz = sum(p.z for p in pts) / len(pts)
            return cq.Vector(cx, cy, cz)

        # Fallback: use bbox center in the perpendicular plane, and top position on axis
        c = sbb.center
        if ax == "Y":
            return cq.Vector(c.x, t, c.z)
        if ax == "Z":
            return cq.Vector(c.x, c.y, t)
        return cq.Vector(t, c.y, c.z)

    center_pt = compute_centerline_point(nipple_solid, nbb, axis) if nipple_solid else bb.center

    # Build cutter (2mm diameter)
    hole_r = 1.0
    start_above = 1.0

    if nipple_solid and nbb:
        depth = (top_of(nbb, axis) - ({"X": nbb.xmin, "Y": nbb.ymin, "Z": nbb.zmin}[axis])) + 15.0
        top_val = top_of(nbb, axis)
    else:
        depth = max(rx, ry, rz) + 50.0
        top_val = global_top

    if axis == "Y":
        cutter = cq.Workplane("XZ", origin=(center_pt.x, top_val + start_above, center_pt.z)).circle(hole_r).extrude(-depth)
    elif axis == "Z":
        cutter = cq.Workplane("XY", origin=(center_pt.x, center_pt.y, top_val + start_above)).circle(hole_r).extrude(-depth)
    else:  # X
        cutter = cq.Workplane("YZ", origin=(top_val + start_above, center_pt.y, center_pt.z)).circle(hole_r).extrude(-depth)

    # Prefer cutting just the nipple solid, but fall back to cutting the whole model if needed.
    if nipple_solid and solids:
        try:
            vol_before = nipple_solid.Volume()
        except Exception:
            vol_before = None

        modified_nipple = cq.Workplane("XY").newObject([nipple_solid]).cut(cutter).val()

        try:
            vol_after = modified_nipple.Volume()
        except Exception:
            vol_after = None

        if vol_before is not None and vol_after is not None:
            delta = vol_before - vol_after
            print(f"Nipple volume before={vol_before:.6f} after={vol_after:.6f} delta={delta:.6f} mm^3")
        else:
            delta = None
            print("Warning: could not compute nipple volume delta")

        # If the cut appears to have done nothing, cut the whole model as a safety net.
        if delta is not None and abs(delta) < 1e-6:
            print("Warning: nipple cut had ~0 delta; applying cut to entire model as fallback")
            return model_wp.cut(cutter)

        new_solids = [modified_nipple if s is nipple_solid else s for s in solids]
        return cq.Compound.makeCompound(new_solids)

    return model_wp.cut(cutter)
