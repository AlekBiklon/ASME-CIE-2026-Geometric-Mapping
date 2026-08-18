def my_cad_function(args):
    import os
    import cadquery as cq

    step_fallback = r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/B7A2N74ZJBF9MZHU_1770156951.5787919.step"
    step_path = os.path.expanduser(args.get("input_file", step_fallback))
    wp_all = cq.importers.importStep(step_path)

    solids = wp_all.solids().vals()
    if not solids:
        print("No solids found; returning imported object")
        return wp_all

    def safe_vol(s):
        try:
            return float(s.Volume())
        except Exception:
            return 0.0

    main_solid = max(solids, key=safe_vol)
    other_solids = [s for s in solids if not s.wrapped.IsSame(main_solid.wrapped)]

    print(f"Loaded: {step_path}")
    print(f"Solids: {len(solids)} (editing largest)")

    # --- Event-picked edge bbox center (Fusion capture), used to locate the valve hole ---
    p_evt = cq.Vector(
        (3.8717106819 + 4.7400818107) / 2.0,
        (19.1491185817 + 19.6947210244) / 2.0,
        (18.8707622528 + 20.0707622528) / 2.0,
    )

    # Pre-collect edge info on main solid
    edge_info = []
    for e in main_solid.Edges():
        try:
            edge_info.append((e.BoundingBox().center, float(e.Length()), e))
        except Exception:
            pass

    def nearest_edge_to_point(pt, max_len=300.0):
        best = None
        for c, L, e in edge_info:
            if L > max_len:
                continue
            d = c.sub(pt).Length
            if best is None or d < best[0]:
                best = (d, e)
        return best

    # Determine coordinate scale (Fusion event coords often in cm)
    scale_candidates = [1.0, 10.0, 25.4]
    best_scale = None
    best_d = 1e99
    for s in scale_candidates:
        hit = nearest_edge_to_point(cq.Vector(p_evt.x * s, p_evt.y * s, p_evt.z * s))
        if hit:
            d, _ = hit
            if d < best_d:
                best_d = d
                best_scale = s

    if best_scale is None:
        print("Could not determine event scale; returning original")
        return wp_all

    p_target = cq.Vector(p_evt.x * best_scale, p_evt.y * best_scale, p_evt.z * best_scale)
    hit0 = nearest_edge_to_point(p_target)
    if not hit0:
        print("Could not locate seed edge near event point; returning original")
        return wp_all

    d0, seed_edge = hit0
    print(f"Using scale={best_scale:g}; seed edge distance={d0:.4f}")

    # --- OCC helpers for robust cylinder extraction ---
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
    except Exception:
        BRepAdaptor_Surface = None
        GeomAbs_Cylinder = None

    def cyl_axis_and_radius(face):
        if BRepAdaptor_Surface is None:
            return None
        try:
            ad = BRepAdaptor_Surface(face.wrapped, True)
            if ad.GetType() != GeomAbs_Cylinder:
                return None
            cyl = ad.Cylinder()
            ax = cyl.Axis()  # gp_Ax1
            loc = ax.Location()
            dire = ax.Direction()
            axis_loc = cq.Vector(loc.X(), loc.Y(), loc.Z())
            axis_dir = cq.Vector(dire.X(), dire.Y(), dire.Z())
            r = float(cyl.Radius())
            return axis_loc, axis_dir, r
        except Exception:
            return None

    def faces_containing_edge(solid, edge):
        out = []
        for f in solid.Faces():
            try:
                for fe in f.Edges():
                    if fe.wrapped.IsSame(edge.wrapped):
                        out.append(f)
                        break
            except Exception:
                pass
        return out

    def face_area(f):
        try:
            return float(f.Area())
        except Exception:
            return 1e99

    def pick_valve_cyl_face(solid, seed_edge):
        cfaces = faces_containing_edge(solid, seed_edge)
        cyls = []
        for f in cfaces:
            data = cyl_axis_and_radius(f)
            if not data:
                continue
            _axis_loc, _axis_dir, r = data
            if 2.0 <= r <= 20.0:
                cyls.append((face_area(f), r, f))
        if cyls:
            cyls.sort(key=lambda t: (t[0], t[1]))
            return cyls[0][2]
        return None

    cyl_face = pick_valve_cyl_face(main_solid, seed_edge)
    if cyl_face is None:
        print("Could not find valve-hole cylindrical face from seed edge; returning original")
        return wp_all

    data = cyl_axis_and_radius(cyl_face)
    if not data:
        print("Selected face was not a cylinder; returning original")
        return wp_all

    axis_loc, axis_dir, r_hole = data
    # normalize axis_dir
    Ld = (axis_dir.x * axis_dir.x + axis_dir.y * axis_dir.y + axis_dir.z * axis_dir.z) ** 0.5
    if Ld < 1e-9:
        print("Cylinder axis direction invalid; returning original")
        return wp_all
    axis_dir = cq.Vector(axis_dir.x / Ld, axis_dir.y / Ld, axis_dir.z / Ld)

    # Get cylinder-face boundary edges and locate the two end planes by projection t along axis
    edge_ts = []
    for e in cyl_face.Edges():
        try:
            Le = float(e.Length())
            if Le < 0.5:
                continue
            c = e.BoundingBox().center
            t = c.sub(axis_loc).dot(axis_dir)
            edge_ts.append((t, Le, c, e))
        except Exception:
            pass

    if len(edge_ts) < 2:
        print("Not enough usable edges on valve cylinder face; returning original")
        return wp_all

    t_vals = [t for t, _Le, _c, _e in edge_ts]
    t_min = min(t_vals)
    t_max = max(t_vals)
    if abs(t_max - t_min) < 1e-4:
        print("Valve cylinder appears degenerate in axis extent; returning original")
        return wp_all

    p_axis_min = axis_loc.add(axis_dir.multiply(t_min))
    p_axis_max = axis_loc.add(axis_dir.multiply(t_max))

    print(f"Valve-hole cylinder radius≈{r_hole:.3f}mm")
    print(f"End planes t_min={t_min:.3f}, t_max={t_max:.3f}")

    # --- Build 1mm (45deg) chamfer by subtracting conical frustums at both ends ---
    chamfer = 1.0
    eps = 0.02  # small robustness fudge
    h = chamfer + eps
    r_outer = r_hole + chamfer + eps
    r_inner = r_hole - 0.0  # keep exact hole radius at depth

    def make_plane(origin_vec, normal_vec):
        # Choose an xDir perpendicular to normal
        n = normal_vec
        Ln = (n.x * n.x + n.y * n.y + n.z * n.z) ** 0.5
        if Ln < 1e-9:
            n = cq.Vector(0, 0, 1)
            Ln = 1.0
        n = cq.Vector(n.x / Ln, n.y / Ln, n.z / Ln)
        ref = cq.Vector(1, 0, 0) if abs(n.x) < 0.9 else cq.Vector(0, 1, 0)
        xdir = ref.cross(n)
        Lx = (xdir.x * xdir.x + xdir.y * xdir.y + xdir.z * xdir.z) ** 0.5
        if Lx < 1e-9:
            ref = cq.Vector(0, 0, 1)
            xdir = ref.cross(n)
            Lx = (xdir.x * xdir.x + xdir.y * xdir.y + xdir.z * xdir.z) ** 0.5
        xdir = cq.Vector(xdir.x / Lx, xdir.y / Lx, xdir.z / Lx)
        return cq.Plane(origin=origin_vec, normal=n, xDir=xdir)

    def make_chamfer_frustum(p_axis, inward_dir):
        pl = make_plane(p_axis, inward_dir)
        fr = (
            cq.Workplane(pl)
            .circle(r_outer)
            .workplane(offset=h)
            .circle(r_inner)
            .loft(ruled=True, combine=False)
        )
        return fr.val()

    # Define inward directions: from each end, inward points toward the other end
    inward_min = axis_dir  # from t_min toward t_max
    inward_max = axis_dir.multiply(-1)  # from t_max toward t_min

    fr1 = make_chamfer_frustum(p_axis_min, inward_min)
    fr2 = make_chamfer_frustum(p_axis_max, inward_max)

    wp_main = cq.Workplane(obj=main_solid)
    try:
        wp_main = wp_main.cut(fr1).cut(fr2)
        print("Applied 1mm chamfer (via frustum cuts) on both valve-hole ends.")
    except Exception as e:
        print(f"Frustum-cut chamfer failed: {e}; returning original")
        return wp_all

    # Recombine other solids unchanged
    result = wp_main
    for s in other_solids:
        try:
            result = result.union(cq.Workplane(obj=s))
        except Exception:
            try:
                result = cq.Compound.makeCompound([result.val(), s])
            except Exception:
                pass

    return result
