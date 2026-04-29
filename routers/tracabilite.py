# routers/tracabilite.py
# Méthode simple Soft Delete — conforme ISO 14064 et CBAM

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_connection

router = APIRouter()


class RaisonInput(BaseModel):
    raison: str  # obligatoire — pourquoi on supprime/modifie


class ModifInput(BaseModel):
    raison:            str
    nouvelle_quantite: Optional[float] = None
    nouvelle_source:   Optional[str]   = None
    nouvelle_date:     Optional[str]   = None


# ══════════════════════════════════════════════════
# VÉRIFICATION — Avant modification/suppression
# ══════════════════════════════════════════════════

@router.get("/activities/{activity_id}/verifier")
def verifier(activity_id: int):
    """Retourne les infos d'une activité et si elle est modifiable."""
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        # COALESCE: si e.co2_kg existe -> utilise sa valeur sinon -> utilise 0
        cursor.execute("""
            SELECT a.*, COALESCE(e.co2_kg, 0) AS co2_kg 
            FROM activities a
            LEFT JOIN emissions e
                   ON e.activity_id = a.id
                  AND COALESCE(e.actif, true) = true
            WHERE a.id = %s
        """, (activity_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404,
                                detail=f"Activite #{activity_id} non trouvee")
        a = dict(row)
        return {
            "modifiable": a.get("actif", True) is not False,
            "actif":      a.get("actif", True),
            "source":     a["source"],
            "quantity":   a["quantity"],
            "unit":       a["unit"],
            "date":       str(a["date"]),
            "co2_kg":     round(float(a["co2_kg"] or 0), 2)
        }
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════
# SUPPRESSION — Soft Delete simple
# ══════════════════════════════════════════════════

@router.post("/activities/{activity_id}/supprimer")
def supprimer(activity_id: int, data: RaisonInput):
    """
    Suppression simple :
    1. Met actif = false sur l'activité
    2. Met actif = false sur son émission
    3. Enregistre la raison
    C'est tout — pas d'entrée compensatoire.
    """
    conn   = get_connection()
    cursor = conn.cursor()

    try:
        # Vérifie que l'activité existe et est active
        cursor.execute("""
            SELECT id, source, quantity, unit
            FROM activities
            WHERE id = %s AND actif = true
        """, (activity_id,))

        activite = cursor.fetchone()
        if not activite:
            raise HTTPException(
                status_code=404,
                detail=f"Activité #{activity_id} introuvable ou déjà supprimée"
            )

        # Désactive l'activité
        cursor.execute("""
            UPDATE activities
            SET actif  = false,
                raison = %s
            WHERE id = %s
        """, (data.raison, activity_id))

        # Désactive son émission
        cursor.execute("""
            UPDATE emissions
            SET actif = false
            WHERE activity_id = %s
        """, (activity_id,))

        # Journal d'audit
        cursor.execute("""
            INSERT INTO audit_log (activity_id, ancien_id, changement, raison)
            VALUES (%s, %s, %s, %s)
        """, (
            activity_id,
            activity_id,
            f"{activite['quantity']} {activite['unit']} supprimé",
            data.raison
        ))

        conn.commit()

        return {
            "message":       f"✅ Activité #{activity_id} supprimée",
            "id":            activity_id,
            "raison":        data.raison,
            "iso_14064":     "✅ Conforme — donnée conservée, non visible dans calculs"
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════
# MODIFICATION — Soft Delete + nouvelle entrée
# ══════════════════════════════════════════════════

@router.post("/activities/{activity_id}/modifier")
def modifier(activity_id: int, modif: ModifInput):
    """
    Modification simple :
    1. Met actif = false sur l'ancienne
    2. Crée une nouvelle avec les bonnes valeurs
    C'est tout.
    """
    conn   = get_connection()
    cursor = conn.cursor()

    try:
        # Récupère l'activité originale
        cursor.execute("""
            SELECT * FROM activities
            WHERE id = %s AND actif = true
        """, (activity_id,))

        old = cursor.fetchone()
        if not old:
            raise HTTPException(
                status_code=404,
                detail=f"Activité #{activity_id} introuvable ou déjà modifiée"
            )

        # Nouvelles valeurs = anciennes si pas changées
        new_quantity = modif.nouvelle_quantite or old["quantity"]
        new_source   = modif.nouvelle_source   or old["source"]
        new_date     = modif.nouvelle_date      or old["date"]
        # Conserve le display_id de la première version de cette activité
        display_id   = old["original_id"] or activity_id

        # Étape 1 — Désactive l'ancienne
        cursor.execute("""
            UPDATE activities
            SET actif  = false,
                raison = %s
            WHERE id = %s
        """, (f"Modifié — {modif.raison}", activity_id))

        cursor.execute("""
            UPDATE emissions
            SET actif = false
            WHERE activity_id = %s
        """, (activity_id,))

        # Étape 2 — Crée la nouvelle activité avec le même original_id
        cursor.execute("""
            INSERT INTO activities
            (source, quantity, unit, date, actif, raison, original_id)
            VALUES (%s, %s, %s, %s, true, %s, %s)
            RETURNING id
        """, (
            new_source,
            new_quantity,
            old["unit"],
            str(new_date),
            f"Correction de #{display_id} — {modif.raison}",
            display_id
        ))

        new_id = cursor.fetchone()["id"]

        # Étape 3 — Calcule et insère la nouvelle émission
        cursor.execute("""
            SELECT factor, scope FROM emission_factors
            WHERE energy_type = %s
        """, (new_source,))

        factor = cursor.fetchone()
        co2    = 0

        if factor:
            co2 = round(new_quantity * factor["factor"], 2)
            cursor.execute("""
                INSERT INTO emissions (activity_id, co2_kg, scope, actif)
                VALUES (%s, %s, %s, true)
            """, (new_id, co2, factor["scope"]))

        # Journal d'audit
        cursor.execute("""
            INSERT INTO audit_log (activity_id, ancien_id, nouveau_id, changement, raison)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            new_id,
            activity_id,
            new_id,
            f"{old['quantity']} {old['unit']} → {new_quantity} {old['unit']}",
            modif.raison
        ))

        conn.commit()

        return {
            "message":    f"✅ Activité #{activity_id} modifiée",
            "ancien_id":  activity_id,
            "nouveau_id": new_id,
            "avant":      {
                "quantity": old["quantity"],
                "source":   old["source"],
                "date":     str(old["date"])
            },
            "apres": {
                "quantity": new_quantity,
                "source":   new_source,
                "date":     str(new_date),
                "co2_kg":   round(co2, 2)
            },
            "raison":    modif.raison,
            "iso_14064": "✅ Conforme"
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# ══════════════════════════════════════════════════
# HISTORIQUE — Ce que voit l'auditeur
# ══════════════════════════════════════════════════

@router.get("/activities/historique")
def historique():
    """Retourne tout — actif et inactif — pour l'auditeur"""
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            a.id,
            a.source,
            a.quantity,
            a.unit,
            a.date,
            a.actif,
            a.raison,
            a.created_at,
            e.co2_kg,
            e.scope
        FROM activities a
        LEFT JOIN emissions e
            ON e.activity_id = a.id
        ORDER BY a.id DESC
    """)

    rows   = cursor.fetchall()
    toutes = [dict(r) for r in rows]

    actives   = [r for r in toutes if r["actif"]]
    inactives = [r for r in toutes if not r["actif"]]

    cursor.execute("""
        SELECT
            id,
            activity_id,
            ancien_id,
            nouveau_id,
            changement,
            raison,
            created_at
        FROM audit_log
        ORDER BY created_at DESC
    """)
    journal = [dict(r) for r in cursor.fetchall()]

    cursor.close()
    conn.close()

    return {
        "total_co2_kg": round(
            sum(r["co2_kg"] or 0 for r in actives), 2
        ),
        "nb_actives":   len(actives),
        "nb_inactives": len(inactives),
        "actives":      actives,
        "inactives":    inactives,
        "journal":      journal
    }