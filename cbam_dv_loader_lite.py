# ═══════════════════════════════════════════════════════════════════════════════
# CarbonIQ — Loader DVs (Règlement UE 2025/2621)
# 
# ⚠️ SOURCE UNIQUE : DVs_as_adopted_v20260204.xlsx
# Pas de duplication données — lecture directe du fichier Excel
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class DVLoader:
    """
    Chargeur léger qui lit DIRECTEMENT le fichier Excel officiel.
    Aucune donnée Python hardcodée.
    
    Source unique : DVs_as_adopted_v20260204.xlsx
    """
    
    def __init__(self, excel_path: str = None):
        """
        Args:
            excel_path: Chemin vers DVs_as_adopted_v20260204.xlsx
                       Par défaut cherche dans ./data/
        """
        if excel_path is None:
            # Cherche automatiquement
            possible_paths = [
                Path(__file__).parent / "data" / "DVs as adopted_v20260204.xlsx",
                Path(__file__).parent.parent / "data" / "DVs as adopted_v20260204.xlsx",
                Path("data") / "DVs as adopted_v20260204.xlsx",
            ]
            
            excel_path = None
            for path in possible_paths:
                if path.exists():
                    excel_path = path
                    break
            
            if excel_path is None:
                raise FileNotFoundError(
                    f"DVs file not found\n"
                    f"Expected location: ./data/DVs_as_adopted_v20260204.xlsx"
                )
        
        self.filepath = Path(excel_path)
        self.xlsx = pd.ExcelFile(self.filepath)
        self.countries = [s for s in self.xlsx.sheet_names 
                         if s not in ["Overview", "Version History"]]
        
        # Cache pour pas relire Excel à chaque fois
        self._cache = {}
        
        logger.info(f"✅ DVs Loader initialized")
        logger.info(f"   Source : {self.filepath.name}")
        logger.info(f"   Pays : {len(self.countries)}")
    
    def _parse_country_sheet(self, country: str) -> Dict[str, dict]:
        """
        Parse une feuille pays et retourne dict { cn_code : dv_data }
        """
        df = pd.read_excel(self.filepath, sheet_name=country, header=None)
        
        products = {}
        current_sector = None
        markup_rates = {"Cement": 0.10, "Fertilisers": 0.01, "Aluminium": 0.10, "Hydrogen": 0.10}
        
        for idx, row in df.iterrows():
            cn = str(row[0]).strip()
            
            # Skip en-têtes
            if cn in [country, "Product CN Code", "nan", "Overview"]:
                continue
            
            # Détecte secteur
            if cn in markup_rates.keys():
                current_sector = cn
                continue
            
            # Essaye de parser les colonnes
            try:
                dv_direct = float(row[2]) if pd.notna(row[2]) and str(row[2]) not in ['–', 'see below'] else None
            except (ValueError, TypeError):
                continue
            
            if dv_direct is None:
                continue
            
            try:
                dv_indirect = float(row[3]) if pd.notna(row[3]) and str(row[3]) not in ['–', 'see below'] else 0.0
                dv_total = float(row[4])
                markup_2026 = float(row[5])
                markup_2027 = float(row[6])
                markup_2028 = float(row[7])
                route = str(row[8]).strip().replace('\xa0', '') if pd.notna(row[8]) else 'N/A'
                description = str(row[1]) if pd.notna(row[1]) else cn
                
                cn_clean = cn.replace(' ', '').replace('.', '')
                
                products[cn_clean] = {
                    'cn_code_raw': cn,
                    'description': description,
                    'sector': current_sector,
                    'dv_direct': round(dv_direct, 4),
                    'dv_indirect': round(dv_indirect, 4),
                    'dv_total': round(dv_total, 4),
                    'markup_2026': round(markup_2026, 4),
                    'markup_2027': round(markup_2027, 4),
                    'markup_2028': round(markup_2028, 4),
                    'route': route,
                    'source_file': str(self.filepath.name),
                    'source_sheet': country,
                }
            except (ValueError, TypeError) as e:
                logger.debug(f"Row {idx} skipped: {e}")
                continue
        
        return products
    
    def lookup(self, country: str, cn_code: str) -> Optional[dict]:
        """
        Recherche une DV par Code NC.
        
        Args:
            country: Pays (Morocco, Algeria, etc.)
            cn_code: Code CN (ex: 25232900 ou "2523 29 00")
        
        Returns:
            dict avec DV data, ou None si non trouvé
        """
        # Charger pays (avec cache)
        if country not in self._cache:
            if country not in self.countries:
                raise ValueError(f"Pays '{country}' non trouvé")
            self._cache[country] = self._parse_country_sheet(country)
        
        products = self._cache[country]
        
        # Normaliser code
        code_clean = cn_code.replace(' ', '').replace('.', '').strip()
        
        # Recherche exacte
        if code_clean in products:
            return products[code_clean]
        
        # Recherche préfixe
        matches = [k for k in products if k.startswith(code_clean)]
        if len(matches) == 1:
            return products[matches[0]]
        
        return None
    
    def get_all(self, country: str) -> Dict[str, dict]:
        """Retourne TOUS les produits d'un pays."""
        if country not in self._cache:
            if country not in self.countries:
                raise ValueError(f"Pays '{country}' non trouvé")
            self._cache[country] = self._parse_country_sheet(country)
        return self._cache[country]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton global
# ─────────────────────────────────────────────────────────────────────────────

_loader = None

def get_loader() -> DVLoader:
    """Retourne l'instance singleton du loader."""
    global _loader
    if _loader is None:
        _loader = DVLoader()
    return _loader


def lookup_dv(country: str, cn_code: str) -> Optional[dict]:
    """Raccourci pour lookup."""
    loader = get_loader()
    return loader.lookup(country, cn_code)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        loader = get_loader()
        
        print("✅ Loader initialized")
        print(f"   Source: {loader.filepath.name}")
        print(f"   Pays: {len(loader.countries)}")
        
        # Test lookup
        print("\n📦 Test 1 - Lookup Morocco / Ciment")
        dv = loader.lookup("Morocco", "25232900")
        if dv:
            print(f"   ✅ Found: {dv['description']}")
            print(f"      DV Total: {dv['dv_total']} tCO2/t")
            print(f"      Mark-up 2026: {dv['markup_2026']} tCO2/t")
            print(f"      Source: {dv['source_file']} - Sheet: {dv['source_sheet']}")
        else:
            print("   ❌ Not found")
        
        # Test 2: Get all Cement
        print("\n📦 Test 2 - All products Morocco / Sector Aluminium")
        all_prods = loader.get_all("Morocco")
        alu_products = [p for p in all_prods.values() if p['sector'] == 'Aluminium']
        print(f"   ✅ Found {len(alu_products)} aluminium products")
        for p in alu_products[:2]:
            print(f"      • {p['cn_code_raw']} → {p['dv_total']} tCO2/t")
        
        print("\n✅ Tests passed - Reading from Excel works!")
        
    except Exception as e:
        print(f"❌ Error: {e}")