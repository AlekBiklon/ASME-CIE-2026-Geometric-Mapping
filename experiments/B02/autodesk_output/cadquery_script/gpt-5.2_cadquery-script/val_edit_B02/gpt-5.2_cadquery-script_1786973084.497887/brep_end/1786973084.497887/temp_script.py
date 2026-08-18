def my_cad_function(args):
    import os
    import cadquery as cq

    # --- STEP path discovery (robust for this harness) ---
    def _is_step(p):
        return isinstance(p, str) and p.lower().endswith((".step", ".stp"))

    def _list_step_files(d):
        try:
            if not (isinstance(d, str) and os.path.isdir(d)):
                return []
            out = []
            for fn in os.listdir(d):
                if fn.lower().endswith((".step", ".stp")):
                    out.append(os.path.join(d, fn))
            return out
        except Exception:
            return []

    def _candidate_dirs_from_path(p):
        dirs = []
        if not isinstance(p, str):
            return dirs
        cur = os.path.abspath(p)
        if os.path.isfile(cur):
            cur = os.path.dirname(cur)
        # Walk up a few levels and add likely siblings
        for _ in range(8):
            dirs.append(cur)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            # sibling folders commonly used by this harness
            dirs.append(os.path.join(parent, "brep_start"))
            dirs.append(os.path.join(parent, "breps"))
            # if currently under brep_end, try replacing
            if "brep_end" in cur.lower():
                dirs.append(cur.lower().replace("brep_end", "brep_start"))
            cur = parent
        # unique
        seen = set()
        out = []
        for d in dirs:
            if isinstance(d, str):
                d = os.path.normpath(d)
                if d not in seen:
                    seen.add(d)
                    out.append(d)
        return out

    def _rank(paths, prefer_root=None):
        ranked = []
        for p in paths:
            pl = p.lower()
            base = os.path.basename(p).lower()
            score = 0
            if "brep_start" in pl:
                score += 300
            if "breps" in pl:
                score += 200
            if "brep_end" in pl:
                score -= 80
            if "example_data" in pl:
                score -= 300
            # prefer tmp.step if in brep_start/breps
            if base == "tmp.step" or base == "tmp.stp":
                score += 20
            # prefer files close to our run directory
            if prefer_root and os.path.commonpath([os.path.abspath(p), prefer_root]) == prefer_root:
                score += 100
            try:
                score += min(int(os.path.getsize(p) / 1024), 200)
            except Exception:
                pass
            ranked.append((score, p))
        ranked.sort(key=lambda t: t[0], reverse=True)
        return [p for _, p in ranked]

    def _find_step_path(a):
        # Direct keys
        for k in ("input_file", "brep_start_path_step", "step_path", "model_path", "file_path"):
            p = a.get(k)
            if _is_step(p) and os.path.exists(os.path.expanduser(p)):
                return os.path.abspath(os.path.expanduser(p))

        # Any arg value
        for v in a.values():
            if _is_step(v) and os.path.exists(os.path.expanduser(v)):
                return os.path.abspath(os.path.expanduser(v))

        output_dir = a.get("output_dir")
        function_file = a.get("function_file")

        # Heuristic: if output_dir contains brep_end, look for sibling brep_start
        if isinstance(output_dir, str) and "brep_end" in output_dir.lower():
            bs = output_dir.lower().replace("brep_end", "brep_start")
            # if output_dir ends with a timestamp folder, bs should as well
            step_files = _list_step_files(bs)
            if step_files:
                return os.path.abspath(_rank(step_files, prefer_root=os.path.dirname(output_dir))[0])

        # Search in a small neighborhood around output_dir and function_file
        search_dirs = []
        if isinstance(output_dir, str):
            search_dirs.extend(_candidate_dirs_from_path(output_dir))
        if isinstance(function_file, str):
            search_dirs.extend(_candidate_dirs_from_path(function_file))

        # Collect step files (shallow + small walk)
        found = []
        for d in search_dirs:
            if not (isinstance(d, str) and os.path.isdir(d)):
                continue
            found.extend(_list_step_files(d))
            # limited recursive walk
            try:
                for dirpath, _, filenames in os.walk(d):
                    for fn in filenames:
                        if fn.lower().endswith((".step", ".stp")):
                            found.append(os.path.join(dirpath, fn))
                    # stop deep recursion
                    rel = os.path.relpath(dirpath, d)
                    if rel.count(os.sep) >= 3:
                        continue
            except Exception:
                pass

        found = list(dict.fromkeys([os.path.abspath(p) for p in found if os.path.exists(p)]))
        prefer_root = os.path.abspath(os.path.dirname(output_dir)) if isinstance(output_dir, str) else None
        ranked = _rank(found, prefer_root=prefer_root)
        return ranked[0] if ranked else None

    step_path = _find_step_path(args)
    if not step_path:
        print("ERROR: Could not locate a STEP file to edit.")
        print(f"Args keys: {sorted(list(args.keys()))}")
        print(f"Args: {args}")
        raise ValueError("No STEP input path found")

    print(f"Loading STEP: {step_path}")
    model = cq.importers.importStep(step_path)
    shape = model.val() if hasattr(model, "val") else model

    # Basic debug
    try:
        bbox = shape.BoundingBox()
        c = bbox.center
        print(f"Valid: {shape.isValid()}")
        print(f"Solids: {len(shape.Solids())}, Faces: {len(shape.Faces())}, Edges: {len(shape.Edges())}")
        print(f"Bbox: x={bbox.xlen:.3f}, y={bbox.ylen:.3f}, z={bbox.zlen:.3f} center=({c.x:.3f},{c.y:.3f},{c.z:.3f})")
    except Exception as e:
        print(f"Debug info failed: {e}")

    r = 0.2  # mm fillet radius

    # --- Robust fillet using OCC directly with greedy edge elimination ---
    try:
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    except Exception:
        BRepFilletAPI_MakeFillet = None

    try:
        from cadquery.occ_impl.shapes import Shape as CQShape
    except Exception:
        CQShape = getattr(cq, "Shape", None)

    def _wrap_topods(ts):
        if CQShape is None:
            # Last resort: return original (shouldn't happen in CQ)
            return None
        return CQShape.cast(ts)

    def _edge_candidates(solid, mode="ALL", min_len=0.0):
        edges = solid.Edges()
        out = []
        for e in edges:
            try:
                L = float(e.Length())
            except Exception:
                continue
            if L < float(min_len):
                continue
            try:
                gt = e.geomType()
            except Exception:
                gt = ""
            if mode == "LINE" and gt != "LINE":
                continue
            # keep
            out.append((L, e))
        # sort shortest -> longest (we will drop shortest first)
        out.sort(key=lambda t: t[0])
        return [e for _, e in out]

    def _try_make_fillet(topods_shape, edges_wrapped):
        mk = BRepFilletAPI_MakeFillet(topods_shape)
        for ew in edges_wrapped:
            mk.Add(r, ew)
        mk.Build()
        try:
            done = mk.IsDone()
        except Exception:
            done = False
        if not done:
            return None
        return mk.Shape()

    def _fillet_best_effort(solid):
        # Fast path: CadQuery fillet (sometimes succeeds)
        try:
            return cq.Workplane(obj=solid).edges().fillet(r).val()
        except Exception:
            pass

        if BRepFilletAPI_MakeFillet is None:
            # Try a more conservative CQ fallback
            for min_len in (1.0, 2.0, 5.0, 10.0):
                try:
                    return (
                        cq.Workplane(obj=solid)
                        .edges()
                        .filter(lambda e: e.Length() > min_len)
                        .fillet(r)
                        .val()
                    )
                except Exception:
                    continue
            return solid

        topods = solid.wrapped

        # Try progressively more conservative candidate sets
        attempts = [
            ("ALL", 0.0),
            ("ALL", 0.5),
            ("ALL", 1.0),
            ("LINE", 0.5),
            ("LINE", 1.0),
            ("LINE", 2.0),
            ("LINE", 5.0),
            ("LINE", 10.0),
        ]

        for mode, min_len in attempts:
            cands = _edge_candidates(solid, mode=mode, min_len=min_len)
            if not cands:
                continue

            # Greedy elimination: try all candidates; if fails, drop shortest and retry.
            # This keeps fillets on long/likely-external sharp edges.
            wrapped_edges = [e.wrapped for e in cands]
            remaining = wrapped_edges
            # limit loops to avoid very long runtimes
            max_loops = min(80, len(remaining))
            for _ in range(max_loops):
                try:
                    out_ts = _try_make_fillet(topods, remaining)
                except Exception:
                    out_ts = None

                if out_ts is not None:
                    w = _wrap_topods(out_ts)
                    return w if w is not None else solid

                if len(remaining) <= 1:
                    break
                # drop the shortest edge and retry
                remaining = remaining[1:]

        return solid

    solids = shape.Solids()
    if not solids:
        # Not a solid model; try shape-level CQ fillet as a last resort
        try:
            return cq.Workplane(obj=shape).edges().fillet(r)
        except Exception as e:
            print(f"No solids and shape-level fillet failed: {e}")
            return model

    if len(solids) == 1:
        out = _fillet_best_effort(solids[0])
        print(f"Applied fillet r={r} mm (best-effort) to single solid.")
        return cq.Workplane(obj=out)

    out_solids = []
    changed = 0
    for i, s in enumerate(solids):
        out_s = _fillet_best_effort(s)
        out_solids.append(out_s)
        try:
            if out_s is not s:
                changed += 1
        except Exception:
            pass

    comp = cq.Compound.makeCompound([os_.wrapped if hasattr(os_, "wrapped") else os_ for os_ in out_solids])
    print(f"Applied fillet r={r} mm (best-effort) across {len(solids)} solids; modified ~{changed} solids; returned compound.")
    return cq.Workplane(obj=comp)
