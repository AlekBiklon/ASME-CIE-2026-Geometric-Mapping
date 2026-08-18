def my_cad_function(args):
    import os, glob, math
    import cadquery as cq

    def _exists(p):
        return bool(p) and os.path.exists(p)

    def _find_step():
        p = os.path.expanduser(args.get("input_file", "") or "")
        if _exists(p):
            return p

        # Known fallback from task info
        known = [
            r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/B7A2N74ZJBF9MZHU_1770156951.5787919.step",
            r"C:\\PROGRAMING_PYTHON\\2026-08-14_ASME_Hackathon_2026\\neuralCAD-Edit-data\\edit_192_external\\breps\\B7A2N74ZJBF9MZHU_1770156951.5787919.step",
        ]
        for k in known:
            if _exists(k):
                return k

        # Search nearby
        roots = [os.getcwd()]
        ff = args.get("function_file")
        if ff:
            fdir = os.path.dirname(os.path.expanduser(ff))
            roots.extend([fdir, os.path.dirname(fdir), os.path.dirname(os.path.dirname(fdir))])

        common_root = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026"
        if os.path.exists(common_root):
            roots.append(common_root)

        pat = "*B7A2N74ZJBF9MZHU*.step"
        for r0 in roots:
            try:
                hits = glob.glob(os.path.join(r0, "**", pat), recursive=True)
                if hits:
                    hits.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    return hits[0]
            except Exception:
                pass

        return ""

    def _dot(a, b):
        return a.x * b.x + a.y * b.y + a.z * b.z

    def _norm(v):
        L = v.Length
        if L <= 1e-12:
            return cq.Vector(0, 0, 1)
        return v.multiply(1.0 / L)

    def _any_perp(u):
        u = _norm(u)
        a = cq.Vector(1, 0, 0)
        if abs(_dot(u, a)) > 0.95:
            a = cq.Vector(0, 1, 0)
        return _norm(u.cross(a))

    def _cyl_params(face):
        ad = face._geomAdaptor()
        cyl = ad.Cylinder()  # gp_Cylinder
        ax = cyl.Axis()      # gp_Ax1
        loc = ax.Location()
        direc = ax.Direction()
        r = float(cyl.Radius())
        axis_loc = cq.Vector(float(loc.X()), float(loc.Y()), float(loc.Z()))
        axis_dir = _norm(cq.Vector(float(direc.X()), float(direc.Y()), float(direc.Z())))
        return r, axis_dir, axis_loc

    def _axis_span_from_face_vertices(face, axis_loc, axis_dir):
        projs = []
        for e in face.Edges():
            for v in e.Vertices():
                x, y, z = v.toTuple()
                pv = cq.Vector(float(x), float(y), float(z))
                projs.append(_dot(pv.sub(axis_loc), axis_dir))
        if not projs:
            return None
        return min(projs), max(projs)

    def _inward_dir_at_opening(solid, opening_center, axis_dir, hole_r):
        # Sample points near the hole wall (not on axis, which is void)
        perp = _any_perp(axis_dir)
        base = opening_center.add(perp.multiply(hole_r + 0.6))
        eps = 0.8
        try:
            inside_plus = bool(solid.isInside(base.add(axis_dir.multiply(eps)), 1e-3))
            inside_minus = bool(solid.isInside(base.sub(axis_dir.multiply(eps)), 1e-3))
            if inside_plus and not inside_minus:
                return axis_dir
            if inside_minus and not inside_plus:
                return axis_dir.multiply(-1)
        except Exception:
            pass
        return axis_dir

    step_path = _find_step()
    if not _exists(step_path):
        print("STEP not found. args keys:", list(args.keys()))
        return None

    wp = cq.importers.importStep(step_path)
    shape = wp.val() if hasattr(wp, "val") else wp

    # Main solid
    try:
        solids = list(shape.Solids())
    except Exception:
        solids = []
    main = max(solids, key=lambda s: s.Volume()) if solids else shape

    bbox = main.BoundingBox()
    bb_center = cq.Vector(float(bbox.center.x), float(bbox.center.y), float(bbox.center.z))

    chamfer_size = 1.0  # 1mm chamfer

    # Find likely valve-hole cylinder: small-ish radius, short span, far from model center
    cands = []
    for f in main.Faces():
        try:
            if f.geomType() != "CYLINDER":
                continue
            r, axis_dir, axis_loc = _cyl_params(f)
            if not (2.5 <= r <= 12.0):
                continue
            span = _axis_span_from_face_vertices(f, axis_loc, axis_dir)
            if not span:
                continue
            tmin, tmax = span
            length = float(abs(tmax - tmin))
            if length < 2.0 or length > 80.0:
                continue

            fc = f.Center()
            fcv = cq.Vector(float(fc.x), float(fc.y), float(fc.z))
            dist = (fcv.sub(bb_center)).Length

            # Prefer far from center, and r near ~6mm, and short-through thickness
            score = dist + 0.25 * length - 0.6 * abs(r - 6.0)
            cands.append((score, r, axis_dir, axis_loc, tmin, tmax))
        except Exception:
            continue

    if not cands:
        print("No suitable cylindrical face found for valve hole; returning original.")
        return cq.Workplane(obj=main)

    cands.sort(key=lambda t: t[0], reverse=True)
    _, hole_r, axis_dir, axis_loc, tmin, tmax = cands[0]

    c0 = axis_loc.add(axis_dir.multiply(tmin))
    c1 = axis_loc.add(axis_dir.multiply(tmax))

    # Build 45deg chamfer tools (cone frustums) and subtract at both openings.
    # Extension makes boolean more robust while keeping 1mm chamfer at the opening plane.
    tool_ext = 0.25

    def _make_tool(opening_center):
        inward = _inward_dir_at_opening(main, opening_center, axis_dir, hole_r)
        outward = inward.multiply(-1)
        h = chamfer_size + tool_ext
        r_base = hole_r + chamfer_size + tool_ext
        r_top = hole_r
        pnt = opening_center.add(outward.multiply(tool_ext))
        return cq.Solid.makeCone(r_base, r_top, h, pnt=pnt, dir=inward)

    try:
        tool0 = _make_tool(c0)
        tool1 = _make_tool(c1)
        result = main.cut(tool0).cut(tool1)
        return cq.Workplane(obj=result)
    except Exception as ex:
        print("Chamfer boolean cut failed:", ex)
        import traceback
        traceback.print_exc()
        return cq.Workplane(obj=main)
