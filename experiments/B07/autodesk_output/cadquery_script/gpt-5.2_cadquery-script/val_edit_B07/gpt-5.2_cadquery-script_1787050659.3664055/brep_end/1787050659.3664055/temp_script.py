def my_cad_function(args):
    import cadquery as cq
    import os, glob, math

    # --- locate STEP ---
    def _norm(p):
        if not p:
            return None
        p = os.path.expanduser(p)
        p = os.path.normpath(p)
        return p

    def _exists(p):
        p = _norm(p)
        return p if p and os.path.exists(p) else None

    step_path = _exists(args.get("input_file"))

    # Task-provided fallback
    if not step_path:
        step_path = _exists(
            "C:/PROGRAMING_PYTHON/2026-08-14_ASME_Hackathon_2026/neuralCAD-Edit-data/edit_192_external/breps/SUJ2G2UMJQR7PMBX_1757575268.303395.step"
        )

    # Search fallback (newest STEP)
    if not step_path:
        roots = []
        if args.get("output_dir"):
            roots.append(os.path.expanduser(args["output_dir"]))
        if args.get("function_file"):
            roots.append(os.path.dirname(os.path.expanduser(args["function_file"])))
        roots.append(os.getcwd())

        cands = []
        for r in roots:
            if not r or not os.path.isdir(r):
                continue
            for pat in ("**/*.step", "**/*.STEP", "**/*.stp", "**/*.STP"):
                cands.extend(glob.glob(os.path.join(r, pat), recursive=True))
        cands = [c for c in set(cands) if os.path.isfile(c)]
        if cands:
            cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            step_path = cands[0]

    if not step_path:
        print("ERROR: Could not find input STEP file. Args keys:", sorted(list(args.keys())))
        return None

    wp = cq.importers.importStep(step_path)
    shape = wp.val() if hasattr(wp, "val") else wp

    # If multiple objects were imported, make a compound
    try:
        objs = list(getattr(wp, "objects", []))
        if len(objs) > 1:
            shape = cq.Compound.makeCompound(objs)
            print(f"Imported {len(objs)} objects -> compound")
    except Exception:
        pass

    bb = shape.BoundingBox()
    center = bb.center
    plan_dim = max(bb.xlen, bb.zlen)
    max_dim = max(bb.xlen, bb.ylen, bb.zlen)

    print(f"Loaded STEP: {step_path}")
    print(f"BBox lens: x={bb.xlen:.6f}, y={bb.ylen:.6f}, z={bb.zlen:.6f}  plan_dim={plan_dim:.6f}")
    try:
        print(f"Solids: {len(shape.Solids())}, Faces: {len(shape.Faces())}, Edges: {len(shape.Edges())}")
    except Exception:
        pass

    # --- Units heuristic ---
    # This part's measured edge lengths in the source video are ~5.196 mm.
    # The imported model shows edges around 5.196 in model units, so treat units as mm.
    # (If this is wrong, fillets will be obviously off-scale / may fail.)
    if max_dim > 5.0:
        unit = "mm"
        mm_to_u = 1.0
    else:
        unit = "cm"
        mm_to_u = 0.1

    r_outer = 2.0 * mm_to_u  # 2 mm
    r_inner = 1.0 * mm_to_u  # 1 mm
    print(f"Assumed units: {unit} -> fillet radii: outer={r_outer}, inner={r_inner}")

    def _vec_from_vertex(v):
        try:
            x, y, z = v.toTuple()
            return cq.Vector(x, y, z)
        except Exception:
            return cq.Vector(v.X, v.Y, v.Z)

    def _edge_dir_and_len(e):
        vs = e.Vertices()
        if len(vs) < 2:
            return None, 0.0
        p1 = _vec_from_vertex(vs[0])
        p2 = _vec_from_vertex(vs[-1])
        d = p2 - p1
        L = d.Length
        if L < 1e-9:
            return None, 0.0
        return d / L, L

    def _radius_xz(pt):
        return math.hypot(pt.x - center.x, pt.z - center.z)

    def _collect_candidates(s):
        line_edges = []
        for e in s.Edges():
            try:
                if e.geomType() != "LINE":
                    continue
            except Exception:
                continue
            d, L = _edge_dir_and_len(e)
            if d is None:
                continue
            c = e.Center()
            r = _radius_xz(c)
            line_edges.append((e, d, L, r, c))

        # focus on central features (the square/frustum and inner opening)
        r_max_central = 0.25 * plan_dim

        outer_cands = []
        inner_cands = []
        for (e, d, L, r, c) in line_edges:
            if r > r_max_central:
                continue
            ax, ay, az = abs(d.x), abs(d.y), abs(d.z)

            # Inner: nearly vertical Y edges (inner opening)
            if ay > 0.995 and max(ax, az) < 0.05:
                inner_cands.append((e, L, r))
                continue

            # Outer: slanted frustum edges (still mostly Y, but with noticeable X/Z)
            if ay > 0.80 and max(ax, az) > 0.10:
                outer_cands.append((e, L, r))
                continue

        return outer_cands, inner_cands

    def _pick_4_edges_by_radius(cands, prefer="max", bin_frac=0.01):
        if not cands:
            return []
        bin_size = max(1e-6, bin_frac * plan_dim)
        bins = {}
        for (e, L, r) in cands:
            k = int(round(r / bin_size))
            bins.setdefault(k, []).append((e, L, r))

        viable = []
        for k, v in bins.items():
            if len(v) < 4:
                continue
            mr = sum(t[2] for t in v) / len(v)
            mL = sum(t[1] for t in v) / len(v)
            viable.append((mr, mL, v))

        if not viable:
            return []
        viable.sort(key=lambda t: t[0])
        chosen = viable[-1] if prefer == "max" else viable[0]

        # take 4 edges closest to mean length (reduces chance of stray edges)
        mL = chosen[1]
        v_sorted = sorted(chosen[2], key=lambda t: abs(t[1] - mL))
        return [t[0] for t in v_sorted[:4]]

    def _dbg_edges(label, edges, s_for_center):
        if not edges:
            print(f"{label}: none")
            return
        lens, rs = [], []
        # keep same center
        for e in edges:
            try:
                _, L = _edge_dir_and_len(e)
                lens.append(L)
                rs.append(_radius_xz(e.Center()))
            except Exception:
                pass
        if lens and rs:
            print(
                f"{label}: count={len(edges)}  L~{sum(lens)/len(lens):.6f} (min {min(lens):.6f}, max {max(lens):.6f})  r~{sum(rs)/len(rs):.6f}"
            )
        else:
            print(f"{label}: count={len(edges)}")

    # --- select & apply outer fillet (2 mm) ---
    outer_cands0, inner_cands0 = _collect_candidates(shape)
    outer_edges0 = _pick_4_edges_by_radius(outer_cands0, prefer="max")
    _dbg_edges("OUTER edges (2mm)", outer_edges0, shape)

    result = shape
    if outer_edges0:
        try:
            result = result.fillet(r_outer, outer_edges0)
            print("Applied outer fillet")
        except Exception as e:
            print("Outer fillet failed:", e)

    # --- re-select inner edges on updated result & apply inner fillet (1 mm) ---
    outer_cands1, inner_cands1 = _collect_candidates(result)
    inner_edges1 = _pick_4_edges_by_radius(inner_cands1, prefer="min")
    _dbg_edges("INNER edges (1mm)", inner_edges1, result)

    if inner_edges1:
        try:
            result = result.fillet(r_inner, inner_edges1)
            print("Applied inner fillet")
        except Exception as e:
            print("Inner fillet failed:", e)

    return result
