def my_cad_function(args):
    import os
    import cadquery as cq

    # -----------------------------
    # Load STEP (use .step)
    # -----------------------------
    def norm(p):
        if not p:
            return None
        p = str(p).strip().strip('"').strip("'")
        p = os.path.expanduser(p)
        return os.path.normpath(p)

    def load_step(path):
        if path and os.path.exists(path) and os.path.isfile(path) and os.path.getsize(path) > 0:
            return cq.importers.importStep(path)
        return None

    candidates = []
    ip = norm(args.get("input_file"))
    if ip:
        candidates.append(ip)

    # Task fallback (runner may not pass input_file)
    candidates.append(
        norm(
            r"C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/B7A2N74ZJBF9MZHU_1770169581.2959814.step"
        )
    )

    seen = set()
    candidates = [p for p in candidates if p and (p not in seen and not seen.add(p))]

    step_wp = None
    used = None
    for p in candidates:
        step_wp = load_step(p)
        if step_wp is not None:
            used = p
            break
    if step_wp is None:
        raise RuntimeError(f"STEP File could not be loaded. Tried: {candidates}")

    print(f"Loaded STEP: {used}")
    shape = step_wp.val() if hasattr(step_wp, "val") else step_wp

    # -----------------------------
    # Geometry helpers
    # -----------------------------
    def is_same(a, b):
        try:
            return a.isSame(b)
        except Exception:
            try:
                return a.wrapped.IsSame(b.wrapped)
            except Exception:
                return False

    def edge_center_xyz(e):
        try:
            c = e.Center()
            return (float(c.x), float(c.y), float(c.z))
        except Exception:
            bb = e.BoundingBox()
            return (0.5 * (bb.xmin + bb.xmax), 0.5 * (bb.ymin + bb.ymax), 0.5 * (bb.zmin + bb.zmax))

    def edge_radius(e):
        try:
            return float(e.radius())
        except Exception:
            return None

    def vsub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def vdot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def vlen(a):
        return (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5

    def vnorm(a):
        L = vlen(a)
        if L < 1e-12:
            return (0.0, 0.0, 0.0)
        return (a[0] / L, a[1] / L, a[2] / L)

    def shares_edge(face, edge):
        try:
            for ed in face.Edges():
                if is_same(ed, edge):
                    return True
        except Exception:
            pass
        return False

    def infer_chamfer_from_cone(cone_face, axis):
        """Return (dist, dr, dz) inferred from a conical face assumed to be a chamfer."""
        chamfer_dist = None
        dr = None
        dz = None

        cone_circles = [e for e in cone_face.Edges() if e.geomType() == "CIRCLE"]
        if len(cone_circles) < 2:
            return (None, None, None)

        cc = [(e, edge_center_xyz(e), edge_radius(e)) for e in cone_circles]

        # pick two circles with max separation along the cylinder axis
        max_sep = -1.0
        chosen = None
        for i in range(len(cc)):
            for j in range(i + 1, len(cc)):
                sep = abs(vdot(vsub(cc[j][1], cc[i][1]), axis))
                if sep > max_sep:
                    max_sep = sep
                    chosen = (cc[i], cc[j])

        if chosen is None:
            return (None, None, None)

        (_, cA, rA), (_, cB, rB) = chosen
        dz = abs(vdot(vsub(cB, cA), axis))
        if rA is not None and rB is not None:
            dr = abs(rB - rA)

        if dr is not None and (dr > 1e-8 or dz > 1e-8):
            chamfer_dist = 0.5 * (dr + dz)
        elif dz > 1e-8:
            chamfer_dist = dz

        return (chamfer_dist, dr, dz)

    def cone_looks_like_chamfer(conef):
        # chamfer cone should have at least 2 circular edges with different radii
        circ = [e for e in conef.Edges() if e.geomType() == "CIRCLE"]
        if len(circ) < 2:
            return False
        rs = [edge_radius(e) for e in circ]
        rs = [r for r in rs if r is not None]
        if len(rs) < 2:
            return False
        return (max(rs) - min(rs)) > 1e-6

    # -----------------------------
    # Select target: Heatbreak main/biggest cylindrical section
    # Heuristics:
    #   - long cylinder (largest height)
    #   - radius in a plausible band for heatbreak (prefer ~3mm)
    #   - has an existing TOP chamfer (cone sharing top end edge)
    # -----------------------------
    try:
        solids = list(shape.Solids())
    except Exception:
        solids = []
    if not solids:
        solids = [shape]

    print(f"Solids found: {len(solids)}")

    best = None

    for si, s in enumerate(solids):
        try:
            faces = list(s.Faces())
        except Exception:
            continue

        cyl_faces = [f for f in faces if f.geomType() == "CYLINDER"]
        if not cyl_faces:
            continue

        cone_faces = [f for f in faces if f.geomType() == "CONE"]
        cone_faces = [f for f in cone_faces if cone_looks_like_chamfer(f)]
        if not cone_faces:
            continue

        for cf in cyl_faces:
            circ_edges = [e for e in cf.Edges() if e.geomType() == "CIRCLE"]
            if len(circ_edges) < 2:
                continue

            centers = [edge_center_xyz(e) for e in circ_edges]

            # ends = pair of circle edges with maximum center distance
            max_d = -1.0
            pair = None
            for i in range(len(circ_edges)):
                for j in range(i + 1, len(circ_edges)):
                    d = vlen(vsub(centers[j], centers[i]))
                    if d > max_d:
                        max_d = d
                        pair = (i, j)
            if pair is None or max_d < 1e-6:
                continue

            i, j = pair
            e1, e2 = circ_edges[i], circ_edges[j]
            c1, c2 = centers[i], centers[j]
            axis = vnorm(vsub(c2, c1))

            # define top/bottom by global Z of end centers
            if c1[2] <= c2[2]:
                e_bot, c_bot = e1, c1
                e_top, c_top = e2, c2
            else:
                e_bot, c_bot = e2, c2
                e_top, c_top = e1, c1

            # Must have a chamfer cone sharing the TOP end edge
            top_cone = None
            for conef in cone_faces:
                if shares_edge(conef, e_top):
                    top_cone = conef
                    break
            if top_cone is None:
                continue

            # Estimate cylinder radius from end circle edges
            r_top = edge_radius(e_top)
            r_bot = edge_radius(e_bot)
            cyl_r = max([r for r in (r_top, r_bot) if r is not None] or [0.0])

            # Infer chamfer size to help scoring and later application
            ch_dist, ch_dr, ch_dz = infer_chamfer_from_cone(top_cone, axis)
            if ch_dist is None:
                continue

            # Chamfer plausibility: small-ish and not a long taper
            # (avoid selecting conical transitions that aren't edge chamfers)
            if ch_dist > 2.5 or ch_dist < 0.02:
                continue

            # Score: primarily by cylinder height, then prefer heatbreak-ish radius (~3mm)
            score = 1000.0 * float(max_d) + 0.1 * float(cf.Area())

            # Strong preference for long cylinders
            if max_d > 20.0:
                score += 10000.0

            # Prefer ~6mm diameter (~3mm radius)
            if 2.5 <= cyl_r <= 3.5:
                score *= 3.0

            # Prefer small chamfer like the existing one (typically <= 1mm)
            if ch_dist <= 1.0:
                score += 2000.0

            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "solid_index": si,
                    "solid": s,
                    "cyl_face": cf,
                    "axis": axis,
                    "height": max_d,
                    "cyl_r": cyl_r,
                    "top_edge": e_top,
                    "bottom_edge": e_bot,
                    "top_cone": top_cone,
                    "chamfer_dist": ch_dist,
                    "chamfer_dr": ch_dr,
                    "chamfer_dz": ch_dz,
                }

    if best is None:
        print("ERROR: No suitable heatbreak-like cylinder with an existing TOP chamfer found. Returning original.")
        return step_wp

    print("--- Target cylinder ---")
    print(
        f"Target solid index: {best['solid_index']} | cyl_area={best['cyl_face'].Area():.3f} | cyl_height~{best['height']:.3f} | cyl_r~{best['cyl_r']:.3f}"
    )
    print(
        f"Inferred chamfer from top: dr={0.0 if best['chamfer_dr'] is None else best['chamfer_dr']:.4f} "
        f"dz={0.0 if best['chamfer_dz'] is None else best['chamfer_dz']:.4f} (avg={best['chamfer_dist']:.4f})"
    )

    chamfer_dist = float(best["chamfer_dist"])
    chamfer_dist = max(0.02, min(chamfer_dist, 3.0))

    # -----------------------------
    # Apply same chamfer to LOWER edge of the cylinder
    # -----------------------------
    target_solid = best["solid"]
    bottom_edge = best["bottom_edge"]

    wp = cq.Workplane(obj=target_solid)
    sel = wp.edges().filter(lambda e: is_same(e, bottom_edge))

    try:
        n_sel = sel.size()
    except Exception:
        try:
            n_sel = len(sel.vals())
        except Exception:
            n_sel = 0

    print(f"Bottom edge selection count: {n_sel}")
    if n_sel == 0:
        print("WARNING: Could not select bottom edge to chamfer. Returning original.")
        return step_wp

    try:
        mod_solid = sel.chamfer(chamfer_dist).val()
    except Exception as e:
        print(f"Chamfer failed at {chamfer_dist:.4f} mm; retrying smaller. err={e}")
        mod_solid = sel.chamfer(max(0.02, 0.75 * chamfer_dist)).val()

    # -----------------------------
    # Recombine solids
    # -----------------------------
    if len(solids) == 1:
        return mod_solid

    new_solids = []
    replaced = False
    for s in solids:
        if (not replaced) and is_same(s, target_solid):
            new_solids.append(mod_solid)
            replaced = True
        else:
            new_solids.append(s)

    if not replaced:
        new_solids = [mod_solid] + [s for s in solids]

    return cq.Compound.makeCompound(new_solids)
