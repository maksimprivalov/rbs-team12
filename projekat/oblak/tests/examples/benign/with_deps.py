"""
Benigni primer SA zavisnošću (requirements.txt -> cowsay).

Pokazuje ceo lanac: host instalira 'cowsay' u venv/ pri deploy-u, a u microVM-u
je dostupan preko PYTHONPATH-a. 'cowsay' je čist Python (radi bez mreže u VM-u).
"""
import cowsay

cowsay.cow("Zavisnosti rade u microVM-u!")
