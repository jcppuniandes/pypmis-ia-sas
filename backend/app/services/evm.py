from dataclasses import dataclass


@dataclass(frozen=True)
class EVMInput:
    bac: float
    planned_value: float
    earned_percent: float
    actual_cost: float


@dataclass(frozen=True)
class EVMResult:
    pv: float
    ev: float
    ac: float
    spi: float
    cpi: float
    sv: float
    cv: float
    bac: float
    eac: float
    etc: float
    vac: float


class EVMEngine:
    def calculate(self, data: EVMInput) -> EVMResult:
        ev = data.bac * (data.earned_percent / 100)
        pv = data.planned_value
        ac = data.actual_cost
        spi = ev / pv if pv else 0
        cpi = ev / ac if ac else 0
        sv = ev - pv
        cv = ev - ac
        eac = data.bac / cpi if cpi else data.bac
        etc = max(eac - ac, 0)
        vac = data.bac - eac

        return EVMResult(
            pv=round(pv, 2),
            ev=round(ev, 2),
            ac=round(ac, 2),
            spi=round(spi, 3),
            cpi=round(cpi, 3),
            sv=round(sv, 2),
            cv=round(cv, 2),
            bac=round(data.bac, 2),
            eac=round(eac, 2),
            etc=round(etc, 2),
            vac=round(vac, 2),
        )
